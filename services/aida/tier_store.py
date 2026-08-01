#!/usr/bin/env python3
"""Four-tier knowledge pipeline: RAW → PROCESSED → TXT_PIX → JIST.

Aligns with Accessibility Vault / A.I.A.D.A. chat design. Immutable raw
copy + progressive accessibility transforms under the ingest root.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIER_NAMES = ("raw", "processed", "txt_pix", "jist")


def _ym(ts: datetime | None = None) -> tuple[str, str]:
    d = ts or datetime.now(timezone.utc)
    return d.strftime("%Y"), d.strftime("%m")


def knowledgebase_root(ingest_root: Path) -> Path:
    return ingest_root / "_knowledgebase"


def ensure_tier_tree(ingest_root: Path) -> dict[str, Any]:
    root = knowledgebase_root(ingest_root)
    created: list[str] = []
    year, month = _ym()
    for tier in TIER_NAMES:
        p = root / tier / year / month
        p.mkdir(parents=True, exist_ok=True)
        created.append(str(p))
    # per-category tier mirrors (for drop workflow)
    return {"status": "ok", "root": str(root), "created": created}


def tier_dir(ingest_root: Path, tier: str, *, category: str | None = None) -> Path:
    year, month = _ym()
    base = knowledgebase_root(ingest_root) / tier / year / month
    if category:
        base = base / category
    base.mkdir(parents=True, exist_ok=True)
    return base


def store_raw(ingest_root: Path, src: Path, *, category: str, sha256: str) -> dict[str, str]:
    dest_dir = tier_dir(ingest_root, "raw", category=category)
    dest = dest_dir / src.name
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        out = dest
    else:
        if dest.exists():
            dest = dest_dir / f"{src.stem}__{sha256[:8]}{src.suffix}"
        shutil.copy2(src, dest)
    meta = {
        "tier": "raw",
        "path": str(dest),
        "sha256": sha256,
        "original_name": src.name,
        "category": category,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = dest.with_suffix(dest.suffix + ".raw.meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"path": str(dest), "meta_path": str(meta_path), **meta}


def store_processed(
    ingest_root: Path,
    src: Path,
    *,
    category: str,
    stem: str,
    report_snippet: dict[str, Any],
) -> dict[str, str]:
    """Store OCR/assured PDF + accessibility report snippet as PROCESSED tier."""
    dest_dir = tier_dir(ingest_root, "processed", category=category)
    dest = dest_dir / f"{stem}.processed{src.suffix.lower() if src.suffix else '.pdf'}"
    if src.is_file():
        shutil.copy2(src, dest)
    else:
        dest = dest_dir / f"{stem}.processed.note.txt"
        dest.write_text(f"source missing: {src}\n", encoding="utf-8")
    report_path = dest_dir / f"{stem}.accessibility.json"
    report_path.write_text(json.dumps(report_snippet, indent=2), encoding="utf-8")
    return {
        "tier": "processed",
        "path": str(dest),
        "accessibility_report": str(report_path),
    }


def store_txt_pix(
    ingest_root: Path,
    *,
    category: str,
    stem: str,
    markdown: str,
    image_notes: list[str] | None = None,
) -> dict[str, str]:
    """Bare text + pix (OCD/ADD distraction-free) markdown."""
    dest_dir = tier_dir(ingest_root, "txt_pix", category=category)
    md_path = dest_dir / f"{stem}.txt_pix.md"
    images = image_notes or []
    body = [
        f"# Bare text + pix — {stem}",
        "",
        "_Distraction-free export (A.I.D.A.). Formatting stripped for cognitive accessibility._",
        "",
        markdown.strip() or "_(no text extracted)_",
        "",
    ]
    if images:
        body.extend(["## Images / figures", ""])
        for note in images:
            body.append(f"- {note}")
        body.append("")
    md_path.write_text("\n".join(body), encoding="utf-8")
    return {"tier": "txt_pix", "path": str(md_path)}


def store_jist(
    ingest_root: Path,
    *,
    category: str,
    stem: str,
    jist: dict[str, Any],
) -> dict[str, str]:
    dest_dir = tier_dir(ingest_root, "jist", category=category)
    path = dest_dir / f"{stem}.jist.json"
    path.write_text(json.dumps(jist, indent=2), encoding="utf-8")
    md = dest_dir / f"{stem}.jist.md"
    lines = [
        f"# JIST — Just In Simple Terms — {stem}",
        "",
        f"**Emotional risk:** {jist.get('emotional_risk_level', 'unknown')}",
        f"**Authority:** {jist.get('decision_authority', 'prepare_only')}",
        f"**HITL:** {jist.get('hitl_status', 'pending')}",
        "",
        "## Summary",
        "",
        str(jist.get("summary") or ""),
        "",
        "## Points",
        "",
    ]
    for b in jist.get("bullets") or []:
        lines.append(f"- {b}")
    lines.append("")
    if jist.get("tts_script"):
        lines.extend(["## TTS soft relay", "", str(jist["tts_script"]), ""])
    md.write_text("\n".join(lines), encoding="utf-8")
    return {"tier": "jist", "path": str(path), "md_path": str(md)}
