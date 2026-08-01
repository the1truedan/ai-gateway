#!/usr/bin/env python3
"""Prepare-only remediation orchestration (no Adobe/Grackle license assumed).

Safe local actions:
  - PyMuPDF metadata (title, language) + basic structure markers
  - pypdf metadata fallback
  - Remediation plan from scorecard
  - Re-run veraPDF on remediated PDF (caller attaches before/after)

HITL required before treating any remediated file as certified.
Never overwrites RAW tier sources.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _set_pdf_metadata_pypdf(src: Path, dest: Path, *, title: str, lang: str = "en-US") -> dict[str, Any]:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return {"status": "skipped", "error": "pypdf not installed"}

    try:
        reader = PdfReader(str(src))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        meta = {}
        if reader.metadata:
            for k, v in reader.metadata.items():
                if v is not None:
                    meta[k] = v
        meta["/Title"] = title
        meta["/Language"] = lang
        meta["/Producer"] = "A.I.D.A. prepare-only remediation (ai-gateway)"
        writer.add_metadata(meta)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            writer.write(f)
        return {
            "status": "completed",
            "engine": "pypdf",
            "output": str(dest),
            "title": title,
            "lang": lang,
            "actions": ["metadata_title_lang"],
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "engine": "pypdf", "error": str(exc)[:300]}


def remediate_pdf_pymupdf(
    src: Path,
    dest: Path,
    *,
    title: str,
    lang: str = "en-US",
) -> dict[str, Any]:
    """Apply prepare-only accessibility improvements via PyMuPDF.

    Safe automatic steps (not full PDF/UA auto-tag):
      - Set metadata Title / Language / Producer
      - Set document language where supported
      - Ensure a simple outline entry (bookmark) for navigation aid
      - Mark PDF as needing structure review in metadata subject

    Full PDF/UA tagging remains HITL / specialist tooling.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {"status": "skipped", "error": "pymupdf not installed", "engine": "pymupdf"}

    actions: list[str] = []
    try:
        doc = fitz.open(str(src))
        # PyMuPDF set_metadata only accepts known keys (no free-form "language")
        meta = dict(doc.metadata or {})
        clean = {
            "title": title,
            "author": meta.get("author") or "",
            "subject": (
                (meta.get("subject") or "")
                + " | A.I.D.A. prepare-only remediated (HITL required)"
            ).strip(" |")[:500],
            "keywords": meta.get("keywords") or "accessibility,prepare-only,AIDA",
            "creator": meta.get("creator") or "A.I.D.A. ai-gateway",
            "producer": "A.I.D.A. ai-gateway PyMuPDF remediation",
        }
        doc.set_metadata(clean)
        actions.append("metadata_title_lang")

        # Document language (PDF Catalog Lang) when available
        try:
            if hasattr(doc, "set_language"):
                doc.set_language(lang.split("-")[0])
                actions.append("catalog_lang")
        except Exception:  # noqa: BLE001
            pass

        # Simple outline (bookmark) if none — aids PDF2 navigation
        try:
            toc = doc.get_toc(simple=True) or []
            if not toc and doc.page_count > 0:
                # One top-level bookmark to first page
                doc.set_toc([[1, title[:80] or "Document", 1]])
                actions.append("outline_bookmark")
            elif toc:
                actions.append("outline_present")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"outline_skip:{str(exc)[:40]}")

        # Optional: set viewer preferences for single-page continuous (cognitive)
        try:
            if hasattr(doc, "set_page_labels") is False:
                pass
        except Exception:  # noqa: BLE001
            pass

        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(dest), garbage=3, deflate=True, clean=True)
        page_count = doc.page_count
        doc.close()
        return {
            "status": "completed",
            "engine": "pymupdf",
            "output": str(dest),
            "title": title,
            "lang": lang,
            "actions": actions,
            "page_count": page_count,
            "note": (
                "Prepare-only metadata/outline remediation — not full PDF/UA auto-tag. "
                "Re-run veraPDF; HITL before any certification claim."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "engine": "pymupdf", "error": str(exc)[:300], "actions": actions}


def build_remediation_plan(scorecard: dict[str, Any], verapdf: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, str]] = []
    for tid in scorecard.get("failed_technique_ids") or []:
        actions.append(
            {
                "id": f"fix_{tid}",
                "technique": tid,
                "action": "manual_or_tool_remediation",
                "detail": f"Address WCAG PDF technique {tid} (tagging / structure / alt text)",
            }
        )
    for rule in scorecard.get("verapdf_rule_ids") or []:
        actions.append(
            {
                "id": f"verapdf_{rule}",
                "technique": rule,
                "action": "verapdf_clause",
                "detail": f"Resolve veraPDF failed clause {rule}",
            }
        )
    if verapdf.get("pdf_ua_pass") is False:
        actions.append(
            {
                "id": "pdf_ua",
                "technique": "PDF/UA",
                "action": "structure_document",
                "detail": "Add tags, reading order, and document title/lang for PDF/UA",
            }
        )
    ada_flags = (scorecard.get("ada_pre_check") or {}).get("ada_flags") or []
    for flag in ada_flags:
        actions.append(
            {
                "id": f"ada_{flag}",
                "technique": flag,
                "action": "ada_pre_check",
                "detail": f"Resolve pre-check flag: {flag}",
            }
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for a in actions:
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        unique.append(a)

    auto_safe = [
        {
            "id": "metadata_title_lang",
            "action": "pymupdf_or_pypdf_metadata",
            "detail": "Set PDF Title + Language metadata",
        },
        {
            "id": "outline_bookmark",
            "action": "pymupdf_toc",
            "detail": "Add simple outline/bookmark if missing (PDF2)",
        },
        {
            "id": "ocr_text_layer",
            "action": "ocrmypdf",
            "detail": "Searchable text layer via ocrmypdf (pipeline when enabled)",
        },
        {
            "id": "linear_html_export",
            "action": "export_html",
            "detail": "Screen-reader linear HTML + bare txt_pix markdown",
        },
        {
            "id": "revalidate_verapdf",
            "action": "verapdf",
            "detail": "Re-run PDF/UA validation on remediated PDF",
        },
        {
            "id": "opendataloader_tagged_pdf",
            "action": "opendataloader_format_tagged_pdf",
            "detail": (
                "Optional Apache-2.0 auto-tag → Tagged PDF candidate "
                "(not certified PDF/UA; not Acrobat Auto-Tag equivalent)"
            ),
        },
        {
            "id": "structwriter_future",
            "action": "pdfbox_struct_writer_stub",
            "detail": (
                "Future: Docling IR → PDFBox StructTreeRoot/ParentTree/MCID writer "
                "+ veraPDF (multi-sprint; no mature OSS Acrobat Auto-Tag today)"
            ),
        },
    ]
    return {
        "auto_safe_actions": auto_safe,
        "manual_actions": unique[:40],
        "requires_hitl": True,
        "decision_authority": "prepare_only",
        "note": "Auto path does not claim PDF/UA compliance; re-run veraPDF after remediation",
        "adobe_policy": "excluded",
        "tagging_doctrine": (
            "No mature OSS Acrobat Auto-Tag. Docling infers structure; "
            "PDFBox-class can write tags; veraPDF judges; OpenDataLoader is a candidate smoke path."
        ),
    }


def run_safe_remediation(
    pdf_path: Path,
    dest_dir: Path,
    *,
    stem: str,
    scorecard: dict[str, Any],
    verapdf: dict[str, Any],
    title: str | None = None,
    revalidate: bool = True,
) -> dict[str, Any]:
    """Write remediation plan + remediated PDF + optional post-veraPDF."""
    plan = build_remediation_plan(scorecard, verapdf)
    dest_dir.mkdir(parents=True, exist_ok=True)
    plan_path = dest_dir / f"{stem}.remediation_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    doc_title = title or stem.replace("_", " ")
    remediated_path = dest_dir / f"{stem}.remediated.pdf"
    tag_result: dict[str, Any] = {"status": "skipped"}
    meta_result: dict[str, Any] = {"status": "skipped"}

    if pdf_path.is_file() and pdf_path.suffix.lower() == ".pdf":
        tag_result = remediate_pdf_pymupdf(pdf_path, remediated_path, title=doc_title)
        if tag_result.get("status") != "completed":
            # Fallback metadata-only via pypdf
            meta_out = dest_dir / f"{stem}.remediated_meta.pdf"
            meta_result = _set_pdf_metadata_pypdf(pdf_path, meta_out, title=doc_title)
            if meta_result.get("status") == "completed":
                remediated_path = Path(meta_result["output"])
        else:
            meta_result = {"status": "superseded_by_pymupdf"}

    post_verapdf: dict[str, Any] | None = None
    if revalidate and remediated_path.is_file() and remediated_path.suffix.lower() == ".pdf":
        try:
            from verapdf_runner import run_verapdf

            post_verapdf = run_verapdf(remediated_path)
        except Exception as exc:  # noqa: BLE001
            post_verapdf = {"status": "error", "error": str(exc)[:300]}

    # Optional OpenDataLoader free Tagged PDF (candidate, not Acrobat equivalent)
    odl_result: dict[str, Any] = {"status": "skipped"}
    verapdf_after_tagged: dict[str, Any] | None = None
    tagged_path: Path | None = None
    need_tags = verapdf.get("pdf_ua_pass") is False or verapdf.get("pdf_ua_pass") is None
    if pdf_path.is_file() and pdf_path.suffix.lower() == ".pdf" and need_tags:
        try:
            import opendataloader_runner

            odl_result = opendataloader_runner.convert_to_tagged_pdf(
                pdf_path, out_dir=dest_dir, stem=stem
            )
            if odl_result.get("status") == "ok" and odl_result.get("output"):
                tagged_path = Path(str(odl_result["output"]))
                if revalidate and tagged_path.is_file():
                    try:
                        from verapdf_runner import run_verapdf

                        verapdf_after_tagged = run_verapdf(tagged_path)
                        odl_result["verapdf_after_tagged"] = {
                            "pdf_ua_pass": verapdf_after_tagged.get("pdf_ua_pass"),
                            "failed_rules": verapdf_after_tagged.get("failed_rules"),
                            "wcag_score": verapdf_after_tagged.get("wcag_score"),
                            "status": verapdf_after_tagged.get("status"),
                        }
                        odl_result["pdf_ua_certified"] = bool(
                            verapdf_after_tagged.get("pdf_ua_pass") is True
                        )
                    except Exception as exc:  # noqa: BLE001
                        verapdf_after_tagged = {"status": "error", "error": str(exc)[:300]}
                        odl_result["verapdf_after_tagged"] = verapdf_after_tagged
        except Exception as exc:  # noqa: BLE001
            odl_result = {"status": "error", "error": str(exc)[:300], "engine": "opendataloader"}

    composite = float(scorecard.get("composite_score") or 0)
    pdf_ua = verapdf.get("pdf_ua_pass")
    post_ua = (post_verapdf or {}).get("pdf_ua_pass")
    tagged_ua = (verapdf_after_tagged or {}).get("pdf_ua_pass")

    if tagged_ua is True:
        status = "opendataloader_tagged_needs_hitl"
    elif post_ua is True and not plan["manual_actions"]:
        status = "auto_improved_needs_hitl"
    elif tag_result.get("status") == "completed":
        status = "pymupdf_remediated_needs_hitl"
    elif meta_result.get("status") == "completed":
        status = "metadata_fixed_needs_review"
    elif pdf_ua is True and composite >= 90:
        status = "auto_fixed_metadata"
    else:
        status = "needs_manual_review"

    delta: dict[str, Any] = {
        "before_pdf_ua": pdf_ua,
        "after_pdf_ua": post_ua,
        "after_tagged_pdf_ua": tagged_ua,
        "before_failed_rules": verapdf.get("failed_rules"),
        "after_failed_rules": (post_verapdf or {}).get("failed_rules"),
        "after_tagged_failed_rules": (verapdf_after_tagged or {}).get("failed_rules"),
        "before_wcag_score": verapdf.get("wcag_score"),
        "after_wcag_score": (post_verapdf or {}).get("wcag_score"),
        "after_tagged_wcag_score": (verapdf_after_tagged or {}).get("wcag_score"),
    }

    out: dict[str, Any] = {
        "status": status,
        "plan_path": str(plan_path),
        "plan": plan,
        "pymupdf_remediation": tag_result,
        "metadata_remediation": meta_result,
        "opendataloader_tagging": odl_result,
        "tagged_path": str(tagged_path) if tagged_path and tagged_path.is_file() else None,
        "remediated_path": str(remediated_path) if remediated_path.is_file() else None,
        "verapdf_before": {
            "pdf_ua_pass": pdf_ua,
            "failed_rules": verapdf.get("failed_rules"),
            "wcag_score": verapdf.get("wcag_score"),
            "status": verapdf.get("status"),
        },
        "verapdf_after": post_verapdf,
        "verapdf_after_tagged": verapdf_after_tagged,
        "delta": delta,
        "hitl_required": True,
        "decision_authority": "prepare_only",
        "note": (
            "Remediated file is prepare-only; RAW tier unchanged. "
            "HITL before certification claims. Adobe not used. "
            "OpenDataLoader Tagged PDF is a candidate only until veraPDF passes."
        ),
    }
    # Persist before/after next to plan
    delta_path = dest_dir / f"{stem}.remediation_delta.json"
    delta_path.write_text(
        json.dumps({"delta": delta, "verapdf_after": post_verapdf, "status": status}, indent=2),
        encoding="utf-8",
    )
    out["delta_path"] = str(delta_path)
    return out
