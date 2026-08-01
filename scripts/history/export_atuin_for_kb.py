#!/usr/bin/env python3
"""Export Atuin shell history to redacted markdown for OWUI KB + Hister.

Reads ~/.local/share/atuin/history.db (or ATUIN_DB), writes day-chunked
markdown under import-data/staging/dev-history/shell/ (gitignored via import-data/).

Usage:
  ./scripts/history/export_atuin_for_kb.py
  ./scripts/history/export_atuin_for_kb.py --days 30
  ATUIN_CWD_PREFIXES=$HOME/ai-gateway:$HOME/grokcode ./scripts/history/export_atuin_for_kb.py
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "import-data" / "staging" / "dev-history" / "shell"
DEFAULT_DB = Path.home() / ".local" / "share" / "atuin" / "history.db"

# Pure navigation / noise — keep in Atuin terminal; drop from RAG export.
NOISE_CMD = re.compile(
    r"^(?:"
    r"cd(?:\s|$)|ls(?:\s|$)|pwd|clear|exit|history|"
    r"which\s+\S+|type\s+\S+|true|false|:"
    r")\s*$",
    re.IGNORECASE,
)
NOISE_SIMPLE = re.compile(r"^(cd|ls|ll|la|pwd|clear|cls|exit|history)(\s|$)")

SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)\s*[=:]\s*\S+"), r"\1=***REDACTED***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]{12,}"), r"\1***REDACTED***"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "***REDACTED_SK***"),
    (re.compile(r"\bxai-[A-Za-z0-9]{16,}\b"), "***REDACTED_XAI***"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "***REDACTED_GHP***"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "***REDACTED_GHO***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "***REDACTED_GH_PAT***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "***REDACTED_AWS_KEY***"),
    (re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)\S+"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(--password(?:=|\s+))\S+"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(-p\s+)(?!ort\b)\S+"), r"\1***REDACTED***"),  # mysql-style -pSECRET (not -p port)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "***REDACTED_JWT***"),
    (re.compile(r"(?i)(LITELLM_MASTER_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|BOTMEM_[A-Z0-9_]+)\s*[=:]\s*\S+"), r"\1=***REDACTED***"),
]


def redact(cmd: str) -> str:
    out = cmd
    for pat, repl in SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def is_noise(cmd: str) -> bool:
    c = cmd.strip()
    if not c:
        return True
    if NOISE_SIMPLE.match(c):
        # Allow ls with interesting flags only if long — still drop plain ls/cd
        parts = c.split()
        if parts[0] in {"cd", "pwd", "clear", "cls", "exit", "history"}:
            return True
        if parts[0] in {"ls", "ll", "la"} and len(parts) <= 3:
            return True
    return False


def parse_prefixes(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(":") if p.strip()]


def cwd_allowed(cwd: str, prefixes: list[str], include_unknown: bool) -> bool:
    if not prefixes:
        return True
    if cwd in ("", "unknown"):
        return include_unknown
    return any(cwd == p or cwd.startswith(p.rstrip("/") + "/") or cwd.startswith(p) for p in prefixes)


def ns_to_dt(ts_ns: int) -> datetime:
    # Atuin stores nanoseconds since epoch
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc).astimezone()


def load_rows(db: Path, days: int | None) -> list[tuple]:
    if not db.is_file():
        raise SystemExit(f"Atuin DB not found: {db}\nInstall/import first: brew install atuin && atuin import zsh")

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        q = (
            "SELECT timestamp, exit, duration, command, cwd, hostname "
            "FROM history WHERE deleted_at IS NULL"
        )
        params: list = []
        if days is not None and days > 0:
            # approximate: days * 86400 * 1e9 ns
            cutoff = int(datetime.now(tz=timezone.utc).timestamp() * 1_000_000_000) - days * 86400 * 1_000_000_000
            q += " AND timestamp >= ?"
            params.append(cutoff)
        q += " ORDER BY timestamp ASC"
        cur = conn.execute(q, params)
        return list(cur.fetchall())
    finally:
        conn.close()


def project_label(cwd: str, prefixes: list[str]) -> str:
    if cwd in ("", "unknown"):
        return "unknown"
    for p in prefixes:
        base = p.rstrip("/")
        name = Path(base).name
        if cwd == base or cwd.startswith(base + "/"):
            return name or "project"
    # fallback: last path component of home-ish paths
    return Path(cwd).name or "shell"


def write_day_files(
    rows: list[tuple],
    out_dir: Path,
    prefixes: list[str],
    include_unknown: bool,
) -> dict[str, int]:
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    kept = 0
    skipped_noise = 0
    skipped_cwd = 0
    redacted_hits = 0

    for ts, exit_code, duration, command, cwd, hostname in rows:
        cmd = (command or "").strip()
        if is_noise(cmd):
            skipped_noise += 1
            continue
        cwd = cwd or "unknown"
        if not cwd_allowed(cwd, prefixes, include_unknown):
            skipped_cwd += 1
            continue

        safe = redact(cmd)
        if safe != cmd:
            redacted_hits += 1

        dt = ns_to_dt(int(ts))
        day = dt.strftime("%Y-%m-%d")
        proj = project_label(cwd, prefixes)
        time_s = dt.strftime("%H:%M:%S")
        exit_s = str(exit_code) if exit_code is not None else "?"
        # duration is ns in Atuin
        try:
            dur_ms = int(duration) / 1_000_000 if duration and int(duration) > 0 else 0
        except (TypeError, ValueError):
            dur_ms = 0
        dur_s = f"{dur_ms/1000:.1f}s" if dur_ms >= 1000 else (f"{dur_ms:.0f}ms" if dur_ms else "?")

        block = (
            f"## {time_s} · exit {exit_s} · {dur_s} · `{cwd}`\n\n"
            f"```bash\n{safe}\n```\n"
        )
        by_key[(proj, day)].append(block)
        kept += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    # Remove old generated day files under project dirs we manage (not wholesale wipe)
    written = 0
    for (proj, day), blocks in sorted(by_key.items()):
        proj_dir = out_dir / proj
        proj_dir.mkdir(parents=True, exist_ok=True)
        path = proj_dir / f"{day}.md"
        header = (
            f"# Shell history — {proj} — {day}\n\n"
            f"_Exported from Atuin for Open WebUI Knowledge Base + Hister. "
            f"Secrets redacted. Navigation noise omitted._\n\n"
            f"Entries: {len(blocks)}\n\n"
        )
        path.write_text(header + "\n".join(blocks), encoding="utf-8")
        written += 1

    # Index file for discovery
    index_path = out_dir / "README.md"
    projects = sorted({p for p, _ in by_key})
    index_lines = [
        "# Dev shell history export",
        "",
        "Generated by `scripts/history/export_atuin_for_kb.py`.",
        "",
        "## How to use",
        "",
        "1. **Open WebUI:** Workspace → Knowledge → `dev-shell-history` → Sync Directory → this folder.",
        "2. **Hister:** compose mounts this path; search with `type:local` or semantic query.",
        "3. **Grok chats:** stay in OWUI chat import (`run_openwebui_import.sh`), not this KB.",
        "",
        f"## Projects in this export ({len(projects)})",
        "",
    ]
    for p in projects:
        days = sorted(d for pr, d in by_key if pr == p)
        index_lines.append(f"- **{p}**: {len(days)} day file(s) ({days[0]} … {days[-1]})")
    index_lines.append("")
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    return {
        "kept": kept,
        "skipped_noise": skipped_noise,
        "skipped_cwd": skipped_cwd,
        "redacted": redacted_hits,
        "files": written,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("ATUIN_DB", DEFAULT_DB)),
        help="Path to Atuin history.db",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("ATUIN_EXPORT_DIR", DEFAULT_OUT)),
        help="Output directory for markdown day files",
    )
    ap.add_argument(
        "--days",
        type=int,
        default=int(os.environ.get("ATUIN_EXPORT_DAYS", "0") or "0"),
        help="Only export last N days (0 = all)",
    )
    ap.add_argument(
        "--cwd-prefixes",
        default=os.environ.get(
            "ATUIN_CWD_PREFIXES",
            f"{ROOT}:$HOME/grokcode:$HOME/ai-gateway",
        ),
        help="Colon-separated cwd prefixes to include (empty = all)",
    )
    ap.add_argument(
        "--include-unknown-cwd",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include pre-Atuin imports with cwd=unknown (default: true)",
    )
    args = ap.parse_args()

    prefixes = parse_prefixes(args.cwd_prefixes)
    days = args.days if args.days > 0 else None
    rows = load_rows(args.db, days)
    stats = write_day_files(rows, args.out, prefixes, args.include_unknown_cwd)

    print(f"DB:     {args.db}")
    print(f"Out:    {args.out}")
    print(f"Rows:   {len(rows)} scanned")
    print(f"Kept:   {stats['kept']} (noise={stats['skipped_noise']}, cwd={stats['skipped_cwd']})")
    print(f"Files:  {stats['files']} day markdown files")
    print(f"Redact: {stats['redacted']} commands had secrets scrubbed")
    if prefixes:
        print(f"CWD:    {prefixes} (unknown={'yes' if args.include_unknown_cwd else 'no'})")


if __name__ == "__main__":
    main()
