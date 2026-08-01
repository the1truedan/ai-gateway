#!/usr/bin/env python3
"""Prune bloated Grok Build sessions to cut token/context bloat.

Exports missing sessions to import-data, truncates terminal captures,
then removes stale session dirs (keeps N newest per cwd).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
IMPORT_PARSER = ROOT / "scripts" / "import" / "grok_build_parser.py"
sys.path.insert(0, str(IMPORT_PARSER.parent))

from grok_build_parser import discover_sessions, parse_session  # noqa: E402


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def session_mtime(session_dir: Path) -> float:
    candidates = [
        session_dir / "updates.jsonl",
        session_dir / "summary.json",
    ]
    for p in candidates:
        if p.exists():
            return p.stat().st_mtime
    return session_dir.stat().st_mtime


def prune_terminals(session_dir: Path, *, max_file_kb: int, dry_run: bool) -> int:
    terminal = session_dir / "terminal"
    if not terminal.exists():
        return 0
    freed = 0
    limit = max_file_kb * 1024
    for f in terminal.rglob("*"):
        if not f.is_file():
            continue
        size = f.stat().st_size
        if size <= limit:
            continue
        freed += size - limit
        if not dry_run:
            f.write_bytes(f.read_bytes()[:limit])
    return freed


def export_session(session_dir: Path, out_dir: Path, *, dry_run: bool) -> bool:
    session = parse_session(session_dir, include_tools=False)
    if session is None:
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in session.title)[:60]
    fname = f"{safe}_{session.session_id}.json"
    target = out_dir / fname
    if target.exists():
        return True
    payload = {
        "id": "",
        "title": session.title,
        "models": [session.model_id],
        "params": {
            "source": "grok-build",
            "cwd": session.cwd,
            "session_id": session.session_id,
        },
        "history": {"messages": {}, "currentId": None},
        "messages": [
            {
                "id": f"m{i}",
                "role": m.role,
                "content": m.content,
                "timestamp": int(m.timestamp),
            }
            for i, m in enumerate(session.messages)
        ],
        "tags": [],
        "timestamp": int(session.updated_at * 1000),
    }
    if dry_run:
        print(f"  would export -> {target.name}")
        return True
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  exported -> {target.name}")
    return True


def cwd_encoded(cwd: str) -> str:
    return quote(cwd, safe="")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune bloated Grok Build sessions")
    parser.add_argument(
        "--cwd",
        default=str(ROOT),
        help="Project cwd to clean (default: ai-gateway root)",
    )
    parser.add_argument(
        "--sessions-root",
        default=str(Path.home() / ".grok" / "sessions"),
        help="Grok sessions root",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="Keep N newest sessions (default: 1 = current only)",
    )
    parser.add_argument(
        "--keep-id",
        action="append",
        default=[],
        help="Always keep session id (repeatable)",
    )
    parser.add_argument(
        "--export-dir",
        default=str(ROOT / "import-data" / "output" / "grok-build"),
        help="Export JSON before delete",
    )
    parser.add_argument(
        "--terminal-max-kb",
        type=int,
        default=64,
        help="Truncate terminal capture files above this size",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-export", action="store_true")
    args = parser.parse_args()

    sessions_root = Path(args.sessions_root)
    cwd_dir = sessions_root / cwd_encoded(args.cwd)
    if not cwd_dir.exists():
        print(f"No sessions for cwd {args.cwd} at {cwd_dir}")
        return 0

    sessions = sorted(
        [p for p in cwd_dir.iterdir() if p.is_dir() and (p / "updates.jsonl").exists()],
        key=session_mtime,
        reverse=True,
    )
    keep_ids = set(args.keep_id)
    for s in sessions[: args.keep]:
        keep_ids.add(s.name)

    before = dir_size(cwd_dir)
    print(f"cwd: {args.cwd}")
    print(f"sessions: {len(sessions)} | disk: {before / 1e6:.1f} MB | keep: {sorted(keep_ids)}")

    export_dir = Path(args.export_dir)
    terminal_freed = 0
    removed = 0

    for session_dir in sessions:
        sid = session_dir.name
        size_mb = dir_size(session_dir) / 1e6
        summary = {}
        sp = session_dir / "summary.json"
        if sp.exists():
            try:
                summary = json.loads(sp.read_text())
            except json.JSONDecodeError:
                pass
        title = (
            summary.get("session_summary")
            or summary.get("generated_title")
            or sid[:8]
        )
        print(f"\n{sid[:8]}… {size_mb:.1f} MB — {str(title)[:55]}")

        terminal_freed += prune_terminals(
            session_dir,
            max_file_kb=args.terminal_max_kb,
            dry_run=args.dry_run,
        )

        if sid in keep_ids:
            print("  keep")
            continue

        if not args.no_export:
            export_session(session_dir, export_dir, dry_run=args.dry_run)

        if args.dry_run:
            print("  would remove")
            removed += 1
            continue

        shutil.rmtree(session_dir)
        print("  removed")
        removed += 1

    after = dir_size(cwd_dir) if not args.dry_run else before
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = {
        "pruned_at": stamp,
        "cwd": args.cwd,
        "before_mb": round(before / 1e6, 2),
        "after_mb": round(after / 1e6, 2),
        "removed": removed,
        "kept": sorted(keep_ids),
        "terminal_truncated_bytes": terminal_freed,
    }
    log_path = ROOT / "import-data" / "session_prune_log.json"
    if not args.dry_run:
        log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")

    print(f"\nDone: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB | removed {removed}")
    if terminal_freed:
        print(f"Terminal captures truncated: {terminal_freed / 1e3:.0f} KB")
    print("Close stale tabs in Grok TUI: /sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())