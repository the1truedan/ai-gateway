#!/usr/bin/env python3
"""VPAT-style accessibility conformance report seed (prepare-only).

Not a formal VPAT 2.4 legal document — structured export for weekend
certification drills and HITL completion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_vpat(receipt: dict[str, Any]) -> dict[str, Any]:
    acc = receipt.get("accessibility") or {}
    mastery = receipt.get("mastery") or acc.get("mastery") or {}
    verapdf = acc.get("verapdf") or {}
    scorecard = mastery if mastery.get("composite_score") is not None else acc.get("scorecard") or {}

    product = {
        "name": "A.I.D.A. document accessibility prepare path (ai-gateway)",
        "version": "0.2.0",
        "report_id": receipt.get("report_id"),
        "source": (receipt.get("source") or {}).get("original_name")
        or (receipt.get("source") or {}).get("path"),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "evaluation_methods": [
            "veraPDF PDF/UA (when available)",
            "structure heuristics",
            "ada_pre_check",
            "linear HTML export",
            "axe-core on HTML (when npx available)",
            "HITL screen reader (VoiceOver/NVDA/JAWS) — field hitl_screen_reader",
        ],
        "decision_authority": "prepare_only",
        "conformance_claim": "None — prepare-only signals; not a formal ACR/VPAT filing",
    }

    criteria = []
    # Seed from section 508 matrix
    for row in (scorecard.get("section_508") or {}).get("checks") or []:
        criteria.append(
            {
                "criterion": row.get("id"),
                "title": row.get("title"),
                "conformance_level": _map_status(row.get("status")),
                "remarks": ", ".join(row.get("evidence") or []),
            }
        )

    # WCAG PDF techniques
    for tid, row in ((scorecard.get("wcag_pdf_techniques") or {}).get("techniques") or {}).items():
        criteria.append(
            {
                "criterion": tid,
                "title": row.get("title"),
                "sc": row.get("sc"),
                "conformance_level": _map_status(row.get("status")),
                "remarks": "; ".join(row.get("notes") or []),
            }
        )

    return {
        "vpat_seed_version": "2.4-style-seed",
        "product": product,
        "summary": {
            "composite_score": scorecard.get("composite_score") or acc.get("wcag_score"),
            "pdf_ua_pass": acc.get("pdf_ua_pass") or verapdf.get("pdf_ua_pass"),
            "legal_risk_level": scorecard.get("legal_risk_level"),
            "hitl_screen_reader": acc.get("hitl_screen_reader", "pending"),
            "remediation_status": (receipt.get("remediation") or {}).get("status"),
        },
        "criteria": criteria,
        "contact": {
            "notes": "Complete HITL screen-reader verification before any external certification use",
        },
    }


def _map_status(status: str | None) -> str:
    s = (status or "").lower()
    if s in ("pass_signal", "likely_pass", "pass"):
        return "Supports (signal)"
    if s in ("fail_signal", "fail"):
        return "Does Not Support (signal)"
    if s in ("partial", "review"):
        return "Partially Supports (signal)"
    if s in ("not_evaluated", "unknown", "skipped"):
        return "Not Evaluated"
    return "Not Evaluated"


def write_vpat(receipt: dict[str, Any], dest_dir: Path, stem: str) -> dict[str, str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    data = build_vpat(receipt)
    json_path = dest_dir / f"{stem}.vpat_seed.json"
    md_path = dest_dir / f"{stem}.vpat_seed.md"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    lines = [
        f"# VPAT-style seed — {stem}",
        "",
        f"**Report:** {data['product'].get('report_id')}",
        f"**Date:** {data['product'].get('date')}",
        f"**Authority:** prepare_only — not a formal ACR",
        "",
        "## Summary",
        "",
        f"- Composite score: {data['summary'].get('composite_score')}",
        f"- PDF/UA: {data['summary'].get('pdf_ua_pass')}",
        f"- Risk: {data['summary'].get('legal_risk_level')}",
        f"- HITL screen reader: {data['summary'].get('hitl_screen_reader')}",
        "",
        "## Criteria (signals)",
        "",
    ]
    for c in data["criteria"][:40]:
        lines.append(
            f"- **{c.get('criterion')}** — {c.get('title')}: {c.get('conformance_level')}"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"vpat_json": str(json_path), "vpat_md": str(md_path)}
