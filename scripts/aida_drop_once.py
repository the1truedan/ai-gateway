#!/usr/bin/env python3
"""One-shot A.I.D.A. process for a local file (no server required).

Usage:
  ./scripts/aida_drop_once.py /path/to/doc.pdf --category medical
  ./scripts/aida_drop_once.py /path/to/doc.pdf --no-llm
  ./scripts/aida_drop_once.py --watch-tick
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_VENV_DIR = ROOT / "services" / "aida" / ".venv"
_VENV_PY = _VENV_DIR / "bin" / "python"
# Prefer service venv so pymupdf / fastapi deps resolve (venv python may
# resolve() to the same system binary — check sys.prefix, not only path).
if _VENV_PY.is_file() and not str(Path(sys.prefix).resolve()).startswith(
    str(_VENV_DIR.resolve())
):
    os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

sys.path.insert(0, str(ROOT / "services" / "aida"))

import pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="A.I.D.A. one-shot document pass")
    ap.add_argument("path", nargs="?", help="PDF/image path")
    ap.add_argument("--category", default=None, help="medical|insurance|legal|…")
    ap.add_argument("--claim", action="store_true", help="Use watch lifecycle claim")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--consent-id", default=None)
    ap.add_argument("--watch-tick", action="store_true", help="Drain _incoming folders")
    ap.add_argument("--ensure-tree", action="store_true")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if args.health:
        print(json.dumps(pipeline.health_snapshot(), indent=2))
        return 0

    if args.ensure_tree:
        print(json.dumps(pipeline.ensure_drop_tree(), indent=2))
        return 0

    if args.watch_tick:
        print(json.dumps(
            pipeline.process_watch_tick(
                limit=args.limit,
                execute_ocr=not args.no_ocr,
                use_llm=not args.no_llm,
            ),
            indent=2,
        ))
        return 0

    if not args.path:
        ap.error("path required unless --watch-tick / --health / --ensure-tree")

    result = pipeline.process_document(
        args.path,
        category=args.category,
        claim=args.claim,
        execute_ocr=not args.no_ocr,
        force_ocr=args.force_ocr,
        use_llm=not args.no_llm,
        consent_id=args.consent_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
