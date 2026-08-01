#!/usr/bin/env python3
"""Thin MANAGER document-output orchestrator (A.I.D.A. Phase 4+).

Picks output kind from style_recommendation + intent, then chains:
  officecli generate → (docx) adeu redline → receipt with a11y next steps.

Prepare-only; never submit_ready. PHI path uses local LiteLLM via officecli External Mode.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import adeu_runner
import officecli_runner
import style_packs

# style_id → preferred officecli kind
_STYLE_KIND: dict[str, str] = {
    "scientific-imrad-icmje": "docx",
    "apa-7": "docx",
    "ama": "docx",
    "cmos-notes-bib": "docx",
    "gpo": "docx",
    "plain-care": "docx",
}

# intent keywords → kind override
_INTENT_KIND: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(deck|slides?|pptx|powerpoint|briefing)\b", re.I), "pptx"),
    (re.compile(r"\b(spreadsheet|xlsx|workbook|tracker|pipeline|budget table)\b", re.I), "xlsx"),
    (re.compile(r"\b(dashboard report|workbook.?backed report)\b", re.I), "report"),
    (re.compile(r"\b(memo|letter|brief|one.?pager|manuscript|proposal|docx)\b", re.I), "docx"),
]


def plan_output(
    *,
    topic: str,
    body: str | None = None,
    category: str | None = None,
    intent: str | None = None,
    kind: str | None = None,
    style_id: str | None = None,
) -> dict[str, Any]:
    """Dry plan: style recommendation + resolved kind + chain steps (no generation)."""
    text = "\n".join(
        x for x in [topic, intent or "", body or ""] if x
    ).strip()
    style_rec = (
        {"style_id": style_id, "confidence": 1.0, "rationale": "caller_forced"}
        if style_id
        else style_packs.recommend_style(text, doc_kind=None, category=category)
    )
    sid = str(style_rec.get("style_id") or "plain-care")
    pack = style_packs.load_pack(sid)
    resolved_kind = _resolve_kind(
        kind=kind,
        style_id=sid,
        intent=intent or topic,
        body=body or "",
    )
    chain = ["officecli_generate"]
    if resolved_kind == "docx":
        chain.append("adeu_redline_optional")
    chain.append("aida_a11y_export_optional")
    return {
        "status": "ok",
        "topic": topic,
        "category": category,
        "style_recommendation": style_rec,
        "style_pack": {
            "style_id": sid,
            "name": pack.get("name"),
            "structure": pack.get("structure"),
            "cite_processor": pack.get("cite_processor"),
            "body_sections": pack.get("body"),
            "front_matter": pack.get("front_matter"),
        },
        "kind": resolved_kind,
        "chain": chain,
        "decision_authority": "prepare_only",
        "submit_ready": False,
        "manager_role": "document_output_orchestrator",
    }


def _resolve_kind(
    *,
    kind: str | None,
    style_id: str,
    intent: str,
    body: str,
) -> str:
    if kind and kind.strip().lower() in officecli_runner.KIND_EXTS:
        return kind.strip().lower()
    blob = f"{intent}\n{body}"
    for pat, k in _INTENT_KIND:
        if pat.search(blob):
            return k
    return _STYLE_KIND.get(style_id, "docx")


def _build_prompt(
    *,
    topic: str,
    body: str | None,
    pack: dict[str, Any],
    kind: str,
    intent: str | None,
) -> str:
    name = pack.get("name") or pack.get("style_id") or "house style"
    sections = pack.get("body") or pack.get("front_matter") or []
    sec_line = ", ".join(str(s) for s in sections[:12]) if sections else ""
    structure = pack.get("structure")
    cite = pack.get("cite_processor")
    parts = [
        f"Create a professional {kind.upper()} titled: {topic}.",
        f"Apply house style: {name}" + (f" (structure={structure})." if structure else "."),
    ]
    if sec_line:
        parts.append(f"Include these sections when relevant: {sec_line}.")
    if cite:
        parts.append(f"Citation preference: {cite} — do not invent sources or DOIs.")
    if intent:
        parts.append(f"User intent: {intent.strip()}")
    if body and body.strip():
        parts.append("Source material / brief (do not invent PHI beyond this text):\n" + body.strip()[:12000])
    parts.append(
        "Rules: prepare-only draft; no patient identifiers unless present in source; "
        "no fabricated medical/legal conclusions; short actionable language; hierarchical headings."
    )
    if kind == "pptx":
        parts.append("Prefer 4–7 slides; one idea per slide; text-only (no image generation required).")
    if kind == "xlsx":
        parts.append("Include header row, example placeholder rows only, clear column names.")
    return "\n\n".join(parts)


def run_document_output(
    *,
    topic: str,
    body: str | None = None,
    category: str = "legal",
    intent: str | None = None,
    kind: str | None = None,
    style_id: str | None = None,
    mode: str = "fast",
    redline: bool = True,
    edits: list[dict[str, Any]] | None = None,
    auto_style_edits: bool = True,
    report_workbook: str | None = None,
    no_images: bool = True,
) -> dict[str, Any]:
    """Execute plan: officecli → optional adeu → orchestration receipt."""
    t0 = time.perf_counter()
    plan = plan_output(
        topic=topic,
        body=body,
        category=category,
        intent=intent,
        kind=kind,
        style_id=style_id,
    )
    resolved_kind = plan["kind"]
    pack = style_packs.load_pack(str(plan["style_recommendation"].get("style_id") or "plain-care"))
    prompt = _build_prompt(
        topic=topic,
        body=body,
        pack=pack,
        kind=resolved_kind,
        intent=intent,
    )

    gen = officecli_runner.generate(
        resolved_kind,
        topic,
        prompt=prompt,
        category=category,
        mode=mode,
        no_images=no_images,
        file=report_workbook,
        force_external=True,
        allow_publish=False,
        style=str(pack.get("style_id") or "") or None,
        audience=intent,
    )

    steps: list[dict[str, Any]] = [
        {"step": "plan", "status": "ok", "kind": resolved_kind, "style": plan["style_recommendation"]},
        {"step": "officecli_generate", "status": gen.get("status"), "result": gen},
    ]

    redline_result: dict[str, Any] | None = None
    final_docx = gen.get("output") if resolved_kind == "docx" else None

    if (
        redline
        and resolved_kind == "docx"
        and gen.get("status") == "ok"
        and gen.get("output")
    ):
        edit_list = list(edits or [])
        if auto_style_edits and not edit_list:
            edit_list = _default_style_edits(topic=topic, style_id=str(pack.get("style_id")))
        if edit_list:
            from pipeline import ingest_root, CATEGORIES

            cat = category if category in CATEGORIES else "_unsorted"
            out_dir = ingest_root() / cat / "_prep" / "document_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(str(gen["output"])).stem
            redlined = out_dir / f"{stem}.redlined.docx"
            redline_result = adeu_runner.apply_edits(
                gen["output"],
                edit_list,
                out_path=redlined,
                author="A.I.D.A. document_output",
            )
            steps.append(
                {
                    "step": "adeu_redline",
                    "status": redline_result.get("status"),
                    "result": redline_result,
                }
            )
            if redline_result.get("status") == "ok" and redline_result.get("output"):
                final_docx = redline_result["output"]
        else:
            steps.append(
                {
                    "step": "adeu_redline",
                    "status": "skipped",
                    "reason": "no edits and auto_style_edits produced empty list",
                }
            )
    elif resolved_kind != "docx":
        steps.append({"step": "adeu_redline", "status": "skipped", "reason": f"kind={resolved_kind}"})

    ok = gen.get("status") == "ok"
    if redline_result and redline_result.get("status") not in (None, "ok", "skipped"):
        # generation ok but redline failed → partial
        overall = "partial" if ok else "error"
    else:
        overall = "ok" if ok else "error"

    receipt = {
        "status": overall,
        "agent": "document_output",
        "manager_compatible": True,
        "decision_authority": "prepare_only",
        "submit_ready": False,
        "hitl_required": True,
        "plan": plan,
        "prompt_used_preview": prompt[:1500],
        "officecli": {
            "status": gen.get("status"),
            "kind": resolved_kind,
            "output": gen.get("output"),
            "receipt_path": gen.get("receipt_path"),
            "elapsed_ms": gen.get("elapsed_ms"),
            "error": gen.get("error"),
        },
        "adeu": redline_result,
        "artifacts": {
            "generated": gen.get("output"),
            "redlined_docx": final_docx if final_docx != gen.get("output") else None,
            "primary": final_docx or gen.get("output"),
        },
        "next_steps": {
            "adeu_more_edits": bool(final_docx or (resolved_kind == "docx" and gen.get("output"))),
            "aida_ingest_for_a11y": bool(gen.get("output")),
            "style_pack_id": pack.get("style_id"),
            "suggested": [
                "HITL review primary artifact",
                "Optional: POST /v1/adeu/apply for more Track Changes",
                "Optional: export PDF then POST /v1/ingest for veraPDF + linear HTML",
            ],
        },
        "steps": steps,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "timestamp_note": "prepare_only orchestration for M.A.N.A.G.E.R. document_output",
    }

    # Persist orchestration receipt
    try:
        from pipeline import ingest_root, CATEGORIES

        cat = category if category in CATEGORIES else "_unsorted"
        od = ingest_root() / cat / "_prep" / "document_output"
        od.mkdir(parents=True, exist_ok=True)
        safe_topic = re.sub(r"[^\w\-]+", "_", topic)[:40].strip("_") or "doc"
        path = od / f"{safe_topic}.document_output.json"
        path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        receipt["orchestration_receipt"] = str(path)
    except Exception as exc:  # noqa: BLE001
        receipt["orchestration_receipt_error"] = str(exc)[:200]

    return receipt


def _default_style_edits(*, topic: str, style_id: str | None) -> list[dict[str, Any]]:
    """Lightweight, high-precision edits only — avoid ambiguous replaces.

    Default chain skips auto-edits if we cannot craft safe unique targets.
    Callers should pass explicit edits for real redlines.
    """
    # No unreliable global string swaps; empty means skip adeu unless user passed edits.
    _ = (topic, style_id)
    return []
