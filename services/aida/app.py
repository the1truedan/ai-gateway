#!/usr/bin/env python3
"""A.I.D.A. document ingest service for ai-gateway.

Watch-folder + OCR + dual briefs + PDF/UA (veraPDF) + mastery scorecard
(A.I.A.D.A. / A.C.C.E.S.S. merged). Prepare-only — weekend document focus.
Phase 2: form fill + always-available Granite VLM + OpenDataLoader tag candidate.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import adeu_runner
import catalog as a11y_catalog
import document_output as doc_out
import form_fill as form_fill_mod
import officecli_runner
import pipeline
import vpat_export

APP_NAME = "manager-aida"
PORT = int(os.environ.get("AIDA_PORT", "8792"))

app = FastAPI(
    title=APP_NAME,
    description=(
        "A.I.D.A. prepare-only document pipeline with deep-assurance mastery: "
        "watch folder, ocrmypdf, veraPDF PDF/UA, Docling + GraniteDocling VLM option, "
        "OpenDataLoader Tagged PDF candidate, AcroForm fill (ai-pdf-autofiller), "
        "adeu DOCX Track Changes redline, officecli generation (PPTX/DOCX/XLSX), "
        "style packs, WCAG PDF techniques map, Section 508 matrix, axe-core on linear HTML, "
        "dual briefs, JIST, 4-tier knowledge store, remediation plan, VPAT seed, HITL. "
        "PHI defaults to local-only LiteLLM role-phi-local. Adobe excluded. "
        "Phase 4–5: officecli + document_output orchestrator (style→kind→generate→adeu) "
        "for M.A.N.A.G.E.R. document pipeline testing."
    ),
    version="0.5.1",
)


class IngestRequest(BaseModel):
    path: str = Field(..., description="Absolute path to PDF/image on host or mounted volume")
    category: str | None = Field(None, description="medical|insurance|legal|…")
    claim: bool = Field(False, description="Move through _incoming lifecycle")
    execute_ocr: bool = True
    force_ocr: bool = False
    use_llm: bool = True
    use_vlm: bool | None = Field(
        None,
        description="None=env default; true=force GraniteDocling VLM; false=standard Docling only",
    )
    consent_id: str | None = None


class WatchTickRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    execute_ocr: bool = True
    use_llm: bool = True
    wait_stable_s: float = Field(1.5, ge=0, le=30)


class EnsureTreeRequest(BaseModel):
    root: str | None = None


class HitlRequest(BaseModel):
    report_id: str
    hitl_screen_reader: str | None = Field(
        None, description="pending|pass|fail|partial"
    )
    remediation_status: str | None = None
    notes: str = ""
    actor: str = "admin"


class FormFillRequest(BaseModel):
    pdf_path: str = Field(..., description="Absolute path to fillable AcroForm PDF")
    user_data: dict[str, Any] = Field(..., description="JSON field values / profile")
    category: str | None = Field(
        None, description="If set, write filled PDF under category/_prep/forms/"
    )
    out_path: str | None = Field(None, description="Optional explicit output path")
    strict: bool = True
    use_semantic_inference: bool = Field(
        False,
        description="Optional AI field semantics — default OFF for PHI",
    )
    allow_fallback_mapping: bool = False
    consent_id: str | None = None


class FormInspectRequest(BaseModel):
    pdf_path: str


@app.get("/health")
def health() -> dict[str, Any]:
    return pipeline.health_snapshot()


@app.get("/v1/pending")
def pending() -> dict[str, Any]:
    items = pipeline.list_pending()
    return {"count": len(items), "items": items, "root": str(pipeline.ingest_root())}


@app.post("/v1/ensure-tree")
def ensure_tree(req: EnsureTreeRequest | None = None) -> dict[str, Any]:
    root = Path(req.root).expanduser() if req and req.root else None
    return pipeline.ensure_drop_tree(root)


@app.post("/v1/ingest")
def ingest(req: IngestRequest) -> dict[str, Any]:
    try:
        return pipeline.process_document(
            req.path,
            category=req.category,
            claim=req.claim,
            execute_ocr=req.execute_ocr,
            force_ocr=req.force_ocr,
            use_llm=req.use_llm,
            use_vlm=req.use_vlm,
            consent_id=req.consent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc


@app.post("/v1/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    category: str = Form("medical"),
    execute_ocr: bool = Form(True),
    use_llm: bool = Form(True),
    use_vlm: str | None = Form(None),
    consent_id: str | None = Form(None),
) -> dict[str, Any]:
    """Upload a file into category/_incoming then process with claim=True."""
    pipeline.ensure_drop_tree()
    cat = category if category in pipeline.CATEGORIES else "_unsorted"
    incoming = pipeline.ingest_root() / cat / "_incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.bin").name
    dest = incoming / name
    if dest.exists():
        dest = incoming / f"{dest.stem}__upl{dest.suffix}"
    data = await file.read()
    dest.write_bytes(data)
    vlm_flag: bool | None = None
    if use_vlm is not None and str(use_vlm).strip() != "":
        vlm_flag = str(use_vlm).strip().lower() in ("1", "true", "yes", "on")
    try:
        return pipeline.process_document(
            dest,
            category=cat,
            claim=True,
            execute_ocr=execute_ocr,
            use_llm=use_llm,
            use_vlm=vlm_flag,
            consent_id=consent_id,
            wait_stable_s=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc


@app.post("/v1/watch/tick")
def watch_tick(req: WatchTickRequest | None = None) -> dict[str, Any]:
    r = req or WatchTickRequest()
    return pipeline.process_watch_tick(
        limit=r.limit,
        execute_ocr=r.execute_ocr,
        use_llm=r.use_llm,
        wait_stable_s=r.wait_stable_s,
    )


@app.get("/v1/report/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    """Find a report JSON by report_id substring under ingest categories."""
    path = pipeline.find_report_file(report_id)
    if not path:
        raise HTTPException(status_code=404, detail=f"no report for {report_id}")
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    data["_report_file"] = str(path)
    return data


@app.post("/v1/hitl")
def hitl_update(req: HitlRequest) -> dict[str, Any]:
    """Record HITL screen-reader / remediation decisions on a report."""
    try:
        return pipeline.update_hitl(
            req.report_id,
            hitl_screen_reader=req.hitl_screen_reader,
            remediation_status=req.remediation_status,
            notes=req.notes,
            actor=req.actor,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/catalog")
def catalog_list(limit: int = 50) -> dict[str, Any]:
    items = a11y_catalog.list_resources(
        limit=min(max(limit, 1), 200),
        db_path=a11y_catalog.default_db_path(pipeline.ingest_root()),
    )
    return {
        "count": len(items),
        "items": items,
        "db": str(a11y_catalog.default_db_path(pipeline.ingest_root())),
    }


@app.get("/v1/vpat/{report_id}")
def get_vpat(report_id: str) -> dict[str, Any]:
    path = pipeline.find_report_file(report_id)
    if not path:
        raise HTTPException(status_code=404, detail=f"no report for {report_id}")
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("vpat") and Path(str((data.get("vpat") or {}).get("vpat_json") or "")).is_file():
        vpath = Path(data["vpat"]["vpat_json"])
        return json.loads(vpath.read_text(encoding="utf-8"))
    return vpat_export.build_vpat(data)


# ---------------------------------------------------------------------------
# Phase 2 form fill
# ---------------------------------------------------------------------------


@app.get("/v1/forms/recipes")
def forms_recipes() -> dict[str, Any]:
    return {"recipes": form_fill_mod.list_recipes()}


@app.get("/v1/forms/health")
def forms_health() -> dict[str, Any]:
    return form_fill_mod.formfill_available()


@app.post("/v1/forms/inspect")
def forms_inspect(req: FormInspectRequest) -> dict[str, Any]:
    result = form_fill_mod.inspect_acroform(req.pdf_path)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error") or "inspect failed")
    return result


@app.post("/v1/forms/fill")
def forms_fill(req: FormFillRequest) -> dict[str, Any]:
    """Fill AcroForm PDF from JSON. Prepare-only — submit_ready always false."""
    out_path = req.out_path
    if not out_path and req.category:
        cat = req.category if req.category in pipeline.CATEGORIES else "_unsorted"
        forms_dir = pipeline.ingest_root() / cat / "_prep" / "forms"
        forms_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(req.pdf_path).stem
        out_path = str(forms_dir / f"{stem}.filled.pdf")
    elif not out_path:
        # default next to template under _prep/forms if under ingest
        stem = Path(req.pdf_path).stem
        forms_dir = pipeline.ingest_root() / "_unsorted" / "_prep" / "forms"
        forms_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(forms_dir / f"{stem}.filled.pdf")

    result = form_fill_mod.fill_pdf(
        req.pdf_path,
        req.user_data,
        out_path=out_path,
        strict=req.strict,
        use_semantic_inference=req.use_semantic_inference,
        allow_fallback_mapping=req.allow_fallback_mapping,
    )
    result["consent_id"] = req.consent_id or pipeline.CONSENT_DEFAULT
    result["submit_ready"] = False
    result["hitl_required"] = True
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


# ---------------------------------------------------------------------------
# Phase 3 — adeu DOCX redline
# ---------------------------------------------------------------------------


class AdeuExtractRequest(BaseModel):
    docx_path: str
    out_path: str | None = None
    clean_view: bool = True


class AdeuApplyRequest(BaseModel):
    docx_path: str
    edits: list[dict[str, Any]] = Field(
        ...,
        description='e.g. [{"type":"modify","target_text":"old","new_text":"new","comment":"..."}]',
    )
    category: str | None = None
    out_path: str | None = None
    author: str | None = None
    dry_run: bool = False


class AdeuSanitizeRequest(BaseModel):
    docx_path: str
    out_path: str | None = None
    author: str | None = None
    keep_markup: bool = True
    accept_all: bool = False


class AdeuFromBriefRequest(BaseModel):
    markdown: str | None = None
    brief_md_path: str | None = None
    category: str = "legal"
    stem: str = "brief"
    title: str = "Care / advocacy draft"
    edits: list[dict[str, Any]] | None = None
    author: str | None = None


@app.get("/v1/adeu/health")
def adeu_health() -> dict[str, Any]:
    return adeu_runner.adeu_available()


@app.post("/v1/adeu/extract")
def adeu_extract(req: AdeuExtractRequest) -> dict[str, Any]:
    result = adeu_runner.extract_docx(
        req.docx_path, out_path=req.out_path, clean_view=req.clean_view
    )
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post("/v1/adeu/apply")
def adeu_apply(req: AdeuApplyRequest) -> dict[str, Any]:
    out_path = req.out_path
    if not out_path:
        cat = req.category if req.category in pipeline.CATEGORIES else "_unsorted"
        dest_dir = pipeline.ingest_root() / cat / "_prep" / "adeu"
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(req.docx_path).stem
        out_path = str(dest_dir / f"{stem}.redlined.docx")
    result = adeu_runner.apply_edits(
        req.docx_path,
        req.edits,
        out_path=out_path,
        author=req.author,
        dry_run=req.dry_run,
    )
    result["hitl_required"] = True
    result["submit_ready"] = False
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post("/v1/adeu/sanitize")
def adeu_sanitize(req: AdeuSanitizeRequest) -> dict[str, Any]:
    result = adeu_runner.sanitize_docx(
        req.docx_path,
        out_path=req.out_path,
        author=req.author,
        keep_markup=req.keep_markup,
        accept_all=req.accept_all,
    )
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post("/v1/adeu/from-brief")
def adeu_from_brief(req: AdeuFromBriefRequest) -> dict[str, Any]:
    """Markdown or brief path → draft DOCX → optional Track Changes redline."""
    cat = req.category if req.category in pipeline.CATEGORIES else "_unsorted"
    out_dir = pipeline.ingest_root() / cat / "_prep" / "adeu"
    result = adeu_runner.from_brief(
        req.brief_md_path,
        markdown=req.markdown,
        out_dir=out_dir,
        stem=req.stem,
        title=req.title,
        edits=req.edits,
        author=req.author,
    )
    result["hitl_required"] = True
    result["submit_ready"] = False
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


# ---------------------------------------------------------------------------
# Phase 4 — officecli generation (MANAGER document output probe)
# ---------------------------------------------------------------------------


class OfficecliConfigureRequest(BaseModel):
    base_url: str | None = Field(None, description="LiteLLM base (default AIDA_LITELLM_BASE)")
    api_key: str | None = None
    model: str | None = None
    publish: bool = False


class OfficecliGenerateRequest(BaseModel):
    kind: str = Field(..., description="pptx|docx|xlsx|report|img|gif")
    topic: str = Field(..., description="Short title / subject")
    prompt: str | None = Field(None, description="Full generation prompt")
    prompt_file: str | None = None
    category: str = Field(
        "legal",
        description="Ingest category for _prep/officecli output (medical forces external)",
    )
    mode: str = Field("fast", description="fast|best")
    style: str | None = None
    audience: str | None = None
    lang: str | None = None
    no_images: bool = Field(True, description="PPTX: text-only (default true for local speed)")
    file: str | None = Field(None, description="Source XLSX for kind=report")
    out_dir: str | None = None


@app.get("/v1/officecli/health")
def officecli_health() -> dict[str, Any]:
    return officecli_runner.officecli_available()


@app.post("/v1/officecli/configure")
def officecli_configure(req: OfficecliConfigureRequest | None = None) -> dict[str, Any]:
    """Force External Mode config → local LiteLLM (non-interactive)."""
    r = req or OfficecliConfigureRequest()
    return officecli_runner.ensure_external_config(
        base_url=r.base_url,
        api_key=r.api_key,
        model=r.model,
        publish=r.publish,
    )


@app.post("/v1/officecli/generate")
def officecli_generate(req: OfficecliGenerateRequest) -> dict[str, Any]:
    """Generate PPTX/DOCX/XLSX/report via officecli (prepare-only, no publish)."""
    result = officecli_runner.generate(
        req.kind,
        req.topic,
        prompt=req.prompt,
        prompt_file=req.prompt_file,
        out_dir=req.out_dir,
        category=req.category,
        mode=req.mode,
        style=req.style,
        audience=req.audience,
        lang=req.lang,
        no_images=req.no_images,
        file=req.file,
        force_external=True,
        allow_publish=False,
    )
    result["hitl_required"] = True
    result["submit_ready"] = False
    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail=result)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@app.get("/v1/officecli/outputs")
def officecli_outputs(category: str | None = None, limit: int = 50) -> dict[str, Any]:
    return officecli_runner.list_outputs(category=category, limit=min(max(limit, 1), 200))


# ---------------------------------------------------------------------------
# MANAGER document_output orchestrator (style → kind → officecli → adeu)
# ---------------------------------------------------------------------------


class DocumentOutputPlanRequest(BaseModel):
    topic: str
    body: str | None = None
    category: str | None = "legal"
    intent: str | None = None
    kind: str | None = Field(None, description="Force pptx|docx|xlsx|report")
    style_id: str | None = Field(None, description="Force style pack id")


class DocumentOutputRunRequest(BaseModel):
    topic: str
    body: str | None = Field(
        None, description="Brief / source text (caregiver letter draft, notes, etc.)"
    )
    category: str = "legal"
    intent: str | None = Field(
        None, description="e.g. 'advocacy letter', 'exec deck', 'budget tracker'"
    )
    kind: str | None = None
    style_id: str | None = None
    mode: str = "fast"
    redline: bool = Field(True, description="After DOCX generate, apply adeu if edits given")
    edits: list[dict[str, Any]] | None = Field(
        None,
        description="adeu modify edits; if empty, redline step is skipped (safe default)",
    )
    report_workbook: str | None = None
    no_images: bool = True


@app.post("/v1/document-output/plan")
def document_output_plan(req: DocumentOutputPlanRequest) -> dict[str, Any]:
    """Dry-run: style recommendation + kind + chain (no LLM generate)."""
    return doc_out.plan_output(
        topic=req.topic,
        body=req.body,
        category=req.category,
        intent=req.intent,
        kind=req.kind,
        style_id=req.style_id,
    )


@app.post("/v1/document-output/run")
def document_output_run(req: DocumentOutputRunRequest) -> dict[str, Any]:
    """Execute style→kind→officecli→optional adeu. Prepare-only MANAGER probe."""
    result = doc_out.run_document_output(
        topic=req.topic,
        body=req.body,
        category=req.category,
        intent=req.intent,
        kind=req.kind,
        style_id=req.style_id,
        mode=req.mode,
        redline=req.redline,
        edits=req.edits,
        report_workbook=req.report_workbook,
        no_images=req.no_images,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": APP_NAME,
        "version": "0.5.1",
        "docs": "/docs",
        "health": "/health",
        "ingest": "POST /v1/ingest",
        "watch": "POST /v1/watch/tick",
        "forms_fill": "POST /v1/forms/fill",
        "forms_inspect": "POST /v1/forms/inspect",
        "adeu_apply": "POST /v1/adeu/apply",
        "adeu_from_brief": "POST /v1/adeu/from-brief",
        "officecli_generate": "POST /v1/officecli/generate",
        "document_output_plan": "POST /v1/document-output/plan",
        "document_output_run": "POST /v1/document-output/run",
        "hitl": "POST /v1/hitl",
        "catalog": "GET /v1/catalog",
        "vpat": "GET /v1/vpat/{report_id}",
    }
