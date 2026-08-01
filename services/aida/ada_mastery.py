#!/usr/bin/env python3
"""A.I.A.D.A. mastery checks — WCAG PDF techniques, Section 508, ADA pre-check.

Prepare-only scoring for ai-gateway. Not a legal certification; measurable
signals for weekend testing + HITL screen-reader confirmation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# WCAG 2.2 PDF techniques most relevant to caregiving forms (informative map)
WCAG_PDF_TECHNIQUES: dict[str, dict[str, str]] = {
    "PDF1": {"sc": "1.1.1", "title": "Text alternatives for images (Alt entry)"},
    "PDF2": {"sc": "2.4.1/2.4.5", "title": "Bookmarks for navigation"},
    "PDF3": {"sc": "1.3.2", "title": "Correct tab and reading order"},
    "PDF4": {"sc": "1.1.1", "title": "Decorative images as Artifact"},
    "PDF5": {"sc": "3.3.2", "title": "Required form controls indicated"},
    "PDF6": {"sc": "1.3.1", "title": "Table markup for tables"},
    "PDF7": {"sc": "1.1.1/1.3.1", "title": "OCR on scanned PDFs"},
    "PDF8": {"sc": "3.3.2", "title": "Form field labels"},
    "PDF9": {"sc": "3.3.2", "title": "Form field tooltips / descriptions"},
    "PDF10": {"sc": "1.3.1", "title": "Structure elements / tags"},
    "PDF12": {"sc": "2.4.8", "title": "Running headers and footers"},
    "PDF17": {"sc": "1.3.1", "title": "Consistent page numbering"},
}

# Section 508 functional performance criteria (high-level, document-focused)
SECTION_508_CHECKS: list[dict[str, str]] = [
    {"id": "502.2.2", "title": "PDF export / non-web docs support assistive tech"},
    {"id": "504.2", "title": "Word processing / PDF authoring accessibility support"},
    {"id": "504.3", "title": "PDF export preserves structure when authored accessibly"},
    {"id": "E205.4", "title": "WCAG 2.0 Level AA incorporation (proxy via PDF/UA + heuristics)"},
    {"id": "302.1", "title": "Without vision — text layer + SR export"},
    {"id": "302.2", "title": "With limited vision — plain language + high-contrast HTML"},
    {"id": "302.9", "title": "Limited language / cognitive — dual audience + JIST"},
]


def ada_pre_check(
    text: str,
    *,
    doc_type: str = "pdf",
    has_ocr: bool = False,
    extract_chars: int = 0,
    path: Path | None = None,
) -> dict[str, Any]:
    """Preliminary ADA readiness score (MANAGER-compatible shape)."""
    flags: list[str] = []
    score = 100

    t = text or ""
    if not t.strip() and extract_chars < 40:
        flags.append("empty_content")
        score -= 40

    if doc_type in ("pdf", "image", "scan") and not re.search(
        r"(?i)(figure|image|chart|photo|alt[- ]?text)", t[:3000]
    ):
        # Cannot prove alt text in pure text extract — soft flag for image-heavy docs
        if path and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            flags.append("missing_alt_text")
            score -= 15

    # Reading-order heuristic: many short lines with no paragraph flow
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if len(lines) > 40:
        short = sum(1 for ln in lines if len(ln.strip()) < 12)
        if short / max(len(lines), 1) > 0.55:
            flags.append("reading_order_unclear")
            score -= 10

    if re.search(r"(?i)\btable\b", t) and not re.search(
        r"(?i)(column|header|row\s*\d)", t
    ):
        flags.append("table_without_headers")
        score -= 10

    if not has_ocr and extract_chars < 40 and doc_type == "pdf":
        flags.append("likely_scan_needs_ocr")
        score -= 20

    # Contrast cannot be measured from text alone
    if re.search(r"(?i)(watermark|grayed|faded|low.?contrast)", t):
        flags.append("low_contrast_hint")
        score -= 10

    score = max(0, min(100, score))
    return {
        "ada_score": score,
        "ada_flags": flags,
        "wcag_hints": [
            "Provide heading hierarchy (h1→h2→h3)",
            "Add alt-text for charts and images",
            "Ensure logical reading order for screen readers",
            "Offer plain-language summary for complex medical tables",
        ]
        if flags
        else [],
        "vision_impaired_ready": score >= 80 and not flags,
        "engine": "ada_pre_check",
    }


def map_verapdf_to_pdf_techniques(verapdf: dict[str, Any]) -> dict[str, Any]:
    """Map veraPDF failed rules to WCAG PDF technique checklist."""
    issues = list(verapdf.get("issues") or [])
    failed_rules = int(verapdf.get("failed_rules") or 0)
    pdf_ua = verapdf.get("pdf_ua_pass")

    technique_status: dict[str, dict[str, Any]] = {}
    for tid, meta in WCAG_PDF_TECHNIQUES.items():
        technique_status[tid] = {
            **meta,
            "status": "unknown",
            "notes": [],
        }

    # PDF7 OCR: inferred from text layer elsewhere; placeholder here
    if verapdf.get("status") == "unavailable":
        for tid in technique_status:
            technique_status[tid]["status"] = "not_evaluated"
            technique_status[tid]["notes"].append("veraPDF unavailable")
    elif pdf_ua is True and failed_rules == 0:
        for tid in technique_status:
            technique_status[tid]["status"] = "likely_pass"
            technique_status[tid]["notes"].append("PDF/UA compliant (veraPDF)")
    elif pdf_ua is False or failed_rules > 0:
        # Common veraPDF clause prefixes → technique buckets (best-effort)
        clause_map = {
            "7.1": "PDF10",
            "7.2": "PDF3",
            "7.3": "PDF1",
            "7.4": "PDF6",
            "7.5": "PDF8",
            "7.18": "PDF2",
            "6.2": "PDF3",
            "5": "PDF10",
            "1.1": "PDF1",
        }
        for issue in issues:
            m = re.search(r"failed_rule:([0-9.]+)", str(issue))
            if not m:
                continue
            clause = m.group(1)
            # longest prefix match
            mapped = None
            for prefix, tid in sorted(clause_map.items(), key=lambda x: -len(x[0])):
                if clause.startswith(prefix):
                    mapped = tid
                    break
            if mapped and mapped in technique_status:
                technique_status[mapped]["status"] = "fail_signal"
                technique_status[mapped]["notes"].append(f"veraPDF {clause}")
        for tid, row in technique_status.items():
            if row["status"] == "unknown":
                row["status"] = "review"
                row["notes"].append("PDF/UA failed overall — manual review")

    return {
        "engine": "wcag_pdf_techniques_map",
        "source": "verapdf+heuristic",
        "techniques": technique_status,
        "failed_rules": failed_rules,
        "pdf_ua_pass": pdf_ua,
    }


def section_508_matrix(
    *,
    text: str,
    verapdf: dict[str, Any],
    ada: dict[str, Any],
    has_sr_html: bool,
    has_jist: bool,
    has_ocr: bool,
) -> dict[str, Any]:
    """High-level Section 508 functional performance matrix for documents."""
    rows: list[dict[str, Any]] = []
    pdf_ua = verapdf.get("pdf_ua_pass")
    chars = len((text or "").strip())

    for check in SECTION_508_CHECKS:
        cid = check["id"]
        status = "review"
        evidence: list[str] = []

        if cid == "502.2.2":
            if pdf_ua is True:
                status, evidence = "pass_signal", ["pdf_ua_pass"]
            elif pdf_ua is False:
                status, evidence = "fail_signal", ["pdf_ua_fail"]
            elif chars > 100:
                status, evidence = "partial", ["text_layer_present"]
            else:
                status, evidence = "fail_signal", ["thin_or_missing_text"]

        elif cid == "504.2":
            status = "pass_signal" if has_ocr or chars > 100 else "fail_signal"
            evidence = ["ocr_or_text"] if status == "pass_signal" else ["needs_ocr"]

        elif cid == "504.3":
            if pdf_ua is True:
                status, evidence = "pass_signal", ["structure_via_pdf_ua"]
            else:
                status, evidence = "review", ["structure_unproven"]

        elif cid == "E205.4":
            if pdf_ua is True and ada.get("ada_score", 0) >= 80:
                status, evidence = "pass_signal", ["pdf_ua_and_ada_pre"]
            elif pdf_ua is False:
                status, evidence = "fail_signal", ["pdf_ua_fail"]
            else:
                status, evidence = "partial", ["heuristic_only"]

        elif cid == "302.1":
            status = "pass_signal" if (chars > 40 and has_sr_html) else "fail_signal"
            evidence = ["text+sr_html"] if status == "pass_signal" else ["missing_sr_or_text"]

        elif cid == "302.2":
            status = "pass_signal" if has_sr_html else "partial"
            evidence = ["sr_html_high_contrast_css"]

        elif cid == "302.9":
            status = "pass_signal" if has_jist else "partial"
            evidence = ["jist_or_dual_briefs"] if has_jist else ["dual_briefs_only"]

        rows.append({**check, "status": status, "evidence": evidence})

    pass_n = sum(1 for r in rows if r["status"] == "pass_signal")
    fail_n = sum(1 for r in rows if r["status"] == "fail_signal")
    return {
        "engine": "section_508_matrix",
        "note": "Prepare-only functional signals — not a formal 508 determination",
        "pass_signals": pass_n,
        "fail_signals": fail_n,
        "total": len(rows),
        "checks": rows,
    }


def build_mastery_scorecard(
    *,
    text: str,
    verapdf: dict[str, Any],
    heuristic: dict[str, Any],
    ada: dict[str, Any],
    html_a11y: dict[str, Any] | None = None,
    has_sr_html: bool = False,
    has_jist: bool = False,
    has_ocr: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate mastery scorecard for receipt + VPAT seed."""
    techniques = map_verapdf_to_pdf_techniques(verapdf)
    s508 = section_508_matrix(
        text=text,
        verapdf=verapdf,
        ada=ada,
        has_sr_html=has_sr_html,
        has_jist=has_jist,
        has_ocr=has_ocr,
    )

    vp_score = verapdf.get("wcag_score")
    heur_score = float(heuristic.get("wcag_score") or 0.0)
    if verapdf.get("status") == "ok" and vp_score is not None:
        base = float(vp_score)
    else:
        base = heur_score
    if verapdf.get("pdf_ua_pass") is False:
        base = min(base, 45.0)

    ada_score = float(ada.get("ada_score") or 0.0)
    axe_penalty = 0.0
    axe_issues = 0
    if html_a11y and html_a11y.get("status") == "ok":
        axe_issues = int(html_a11y.get("violations_count") or 0)
        axe_penalty = min(25.0, axe_issues * 2.5)

    composite = max(0.0, min(100.0, (base * 0.55) + (ada_score * 0.30) + (15.0 - axe_penalty * 0.4)))
    if axe_penalty:
        composite = max(0.0, composite - axe_penalty * 0.5)

    failed_technique_ids = [
        tid
        for tid, row in (techniques.get("techniques") or {}).items()
        if row.get("status") == "fail_signal"
    ]

    risk = "low"
    if composite < 50 or verapdf.get("pdf_ua_pass") is False:
        risk = "high"
    elif composite < 75 or failed_technique_ids or axe_issues > 3:
        risk = "medium"

    return {
        "composite_score": round(composite, 1),
        "legal_risk_level": risk,
        "ada_pre_check": ada,
        "wcag_pdf_techniques": techniques,
        "section_508": s508,
        "html_a11y": html_a11y or {"status": "skipped"},
        "failed_technique_ids": failed_technique_ids,
        "verapdf_rule_ids": [
            str(i).replace("failed_rule:", "")
            for i in (verapdf.get("issues") or [])
            if str(i).startswith("failed_rule:")
        ],
        "decision_authority": "prepare_only",
        "certification_claim": "none — prepare_only measurable signals for HITL",
    }
