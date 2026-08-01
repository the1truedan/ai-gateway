#!/usr/bin/env python3
"""A.I.D.A. prepare-only document pipeline for ai-gateway.

Mirrors MANAGER ingest plane (D.A.N. drop → A.I.D.A. first_pass) without
importing the full grokcode tree. PHI path defaults to local LiteLLM only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verapdf_runner import run_verapdf

import ada_mastery
import catalog as a11y_catalog
import docling_runner
import adeu_runner
import form_fill as form_fill_mod
import html_a11y
import jist_relay
import officecli_runner
import opendataloader_runner as odl_runner
import remediation as remediation_mod
import style_packs
import tier_store
import vpat_export
# document_output imported lazily in health to avoid circular import at module load

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_INGEST = os.environ.get(
    "AIDA_INGEST_ROOT",
    os.environ.get("MANAGER_INGEST_ROOT", "/Volumes/ai-data/work/ingest"),
)
LITELLM_BASE = os.environ.get("AIDA_LITELLM_BASE", "http://localhost:4000").rstrip("/")
LITELLM_KEY = os.environ.get("AIDA_LITELLM_KEY") or os.environ.get("LITELLM_MASTER_KEY", "")
# PHI-safe default: local tier only
AIDA_MODEL = os.environ.get("AIDA_MODEL", "role-phi-local")
AIDA_ALLOW_REMOTE = os.environ.get("AIDA_ALLOW_REMOTE", "0") == "1"
CONSENT_DEFAULT = os.environ.get("AIDA_CONSENT_ID", "consent-example-full-2026-07-02")
REPORTS_DIR_NAME = "_aida_reports"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
_DOC_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md"}
_SCAN_EXTS = _IMAGE_EXTS | _DOC_EXTS

_REMOTE_MODEL_MARKERS = (
    "openrouter",
    "gemini",
    "gpt-",
    "claude",
    "xai",
    "grok-",
    "anthropic",
    "openai/",
)

LIFECYCLE = ("_incoming", "_processing", "_done", "_error", "_briefs", "_prep")

# Minimal category map (aligned with MANAGER volume_ingest_drops.json)
CATEGORIES: dict[str, dict[str, str]] = {
    "medical": {"doc_kind": "clinical_results", "source_type": "document_drop"},
    "insurance": {"doc_kind": "medicare", "source_type": "document_drop"},
    "legal": {"doc_kind": "form", "source_type": "document_drop"},
    "mail": {"doc_kind": "form", "source_type": "document_drop"},
    "receipts": {"doc_kind": "receipt", "source_type": "receipt"},
    "pharmacy_rx": {"doc_kind": "medication_list", "source_type": "document_drop"},
    "appointments": {"doc_kind": "after_visit_summary", "source_type": "document_drop"},
    "hospice": {"doc_kind": "hospice_form", "source_type": "document_drop"},
    "financial": {"doc_kind": "bill", "source_type": "document_drop"},
    "ssdi_disability": {"doc_kind": "form", "source_type": "document_drop"},
    "timesheets": {"doc_kind": "form", "source_type": "document_drop"},
    "identity": {"doc_kind": "form", "source_type": "screenshot"},
    "home_dme": {"doc_kind": "bill", "source_type": "document_drop"},
    "photos_care": {"doc_kind": "general", "source_type": "screenshot"},
    "education": {"doc_kind": "general", "source_type": "calibre_book"},
    "ebooks": {"doc_kind": "general", "source_type": "calibre_book"},
    "_unsorted": {"doc_kind": "general", "source_type": "document_drop"},
}

_DOC_HINTS = {
    "lab_results": "These numbers describe how your body is doing on specific tests.",
    "clinical_results": "These are clinical results. Your clinician can explain what is normal for you.",
    "medicare": "This form relates to Medicare coverage or billing.",
    "medicaid": "This document involves Medicaid benefits.",
    "bill": "This is a statement of charges. Look for service dates and amounts due.",
    "receipt": "This receipt lists items purchased.",
    "form": "This is an official form. Required fields and deadlines matter.",
    "after_visit_summary": "This after-visit summary captures what happened and what to do next.",
    "medication_list": "This lists current medications with doses and timing.",
    "hospice_form": "This hospice-related form involves election, benefits, or care planning.",
    "insurance_eob": "This is an insurance explanation of benefits — not always a bill.",
    "legal": "This is a legal or rights-related paper. Deadlines and signatures matter.",
    "general": "This document may contain important care or billing information.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_root() -> Path:
    return Path(DEFAULT_INGEST).expanduser()


def assert_phi_model_safe(model: str) -> None:
    m = (model or "").lower()
    if AIDA_ALLOW_REMOTE:
        return
    if any(x in m for x in _REMOTE_MODEL_MARKERS):
        raise ValueError(
            f"AIDA_MODEL={model!r} looks remote/cloud; PHI path requires local tier "
            f"(default role-phi-local). Set AIDA_ALLOW_REMOTE=1 only with explicit policy."
        )


def ensure_drop_tree(root: Path | None = None) -> dict[str, Any]:
    base = root or ingest_root()
    created: list[str] = []
    for util in ("_unsorted", "_quarantine", "_config"):
        p = base / util
        p.mkdir(parents=True, exist_ok=True)
        created.append(str(p))
        if util == "_unsorted":
            for sub in LIFECYCLE:
                sp = p / sub
                sp.mkdir(parents=True, exist_ok=True)
                created.append(str(sp))
    for name in CATEGORIES:
        if name.startswith("_"):
            continue
        cat = base / name
        cat.mkdir(parents=True, exist_ok=True)
        for sub in LIFECYCLE:
            sp = cat / sub
            sp.mkdir(parents=True, exist_ok=True)
            created.append(str(sp))
    tiers = tier_store.ensure_tier_tree(base)
    a11y_catalog.init_db(a11y_catalog.default_db_path(base))
    return {
        "status": "ok",
        "root": str(base),
        "created_count": len(set(created)),
        "knowledgebase": tiers,
        "catalog_db": str(a11y_catalog.default_db_path(base)),
    }


def classify_document_kind(text: str, hint: str | None = None) -> str:
    if hint and hint != "general":
        return hint
    t = (text or "").lower()
    if any(k in t for k in ("explanation of benefits", "eob", "claim number", "allowed amount")):
        return "insurance_eob"
    if any(k in t for k in ("medicare", "cms-", "part a", "part b")):
        return "medicare"
    if any(k in t for k in ("medicaid", "spend-down")):
        return "medicaid"
    if any(k in t for k in ("power of attorney", "guardianship", "attorney", "summons")):
        return "legal"
    if any(k in t for k in ("inr", "hemoglobin", "lab", "test result", "reference range")):
        return "lab_results"
    if any(k in t for k in ("total due", "statement", "balance", "invoice")):
        return "bill"
    if any(k in t for k in ("qty", "subtotal", "receipt", "thank you for shopping")):
        return "receipt"
    if any(k in t for k in ("medication", "prescription", "dosage", "med list")):
        return "medication_list"
    if "hospice" in t:
        return "hospice_form"
    if any(k in t for k in ("after visit", "visit summary", "discharge")):
        return "after_visit_summary"
    return hint or "general"


def initial_phi_flags(text: str) -> list[str]:
    flags: list[str] = []
    t = text or ""
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", t):
        flags.append("ssn_pattern")
    if re.search(r"\b\d{3}-\d{3}-\d{4}\b", t):
        flags.append("phone_pattern")
    if re.search(r"\bMRN\b|\bmedical record\b", t, re.I):
        flags.append("mrn_mention")
    if re.search(r"\bDOB\b|date of birth", t, re.I):
        flags.append("dob_mention")
    if re.search(r"@[\w.-]+\.\w+", t):
        flags.append("email_pattern")
    return flags


def extract_pdf_text(path: Path, max_pages: int = 40) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"text": "", "pages": 0, "engine": "none", "error": "pypdf not installed"}

    try:
        reader = PdfReader(str(path))
        pages = min(len(reader.pages), max_pages)
        chunks: list[str] = []
        for i in range(pages):
            try:
                chunks.append(reader.pages[i].extract_text() or "")
            except Exception:  # noqa: BLE001
                chunks.append("")
        text = "\n".join(chunks).strip()
        return {
            "text": text,
            "pages": len(reader.pages),
            "pages_extracted": pages,
            "engine": "pypdf",
            "chars": len(text),
        }
    except Exception as exc:  # noqa: BLE001
        return {"text": "", "pages": 0, "engine": "pypdf", "error": str(exc)[:300]}


def extract_text(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in {".txt", ".md"}:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {"text": text, "pages": 1, "engine": "text", "chars": len(text)}
        except OSError as exc:
            return {"text": "", "engine": "text", "error": str(exc)}
    if suffix in _IMAGE_EXTS:
        return {
            "text": "",
            "pages": 1,
            "engine": "image",
            "note": "image — OCR via ocrmypdf after image-to-pdf if needed",
        }
    return {"text": "", "engine": "unsupported", "error": f"unsupported suffix {suffix}"}


def ocrmypdf_available() -> bool:
    return shutil.which("ocrmypdf") is not None


def run_ocr(source: Path, dest: Path, *, force: bool = False) -> dict[str, Any]:
    if dest.is_file() and not force and dest.stat().st_size > 0:
        extract = extract_pdf_text(dest)
        if extract.get("chars", 0) > 50:
            return {
                "status": "completed",
                "engine": "ocrmypdf",
                "output": str(dest),
                "note": "reused existing OCR artifact",
                "extract_chars": extract.get("chars"),
            }

    if not ocrmypdf_available():
        return {
            "status": "skipped",
            "engine": "ocrmypdf",
            "note": "ocrmypdf not on PATH",
            "output": None,
        }

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ocrmypdf", "--deskew", "--clean", "--rotate-pages"]
    if force:
        cmd.append("--force-ocr")
    else:
        cmd.append("--skip-text")
    cmd.extend([str(source), str(dest)])

    size_mb = max(1, source.stat().st_size // (1024 * 1024))
    timeout_s = min(3600, max(180, size_mb * 45))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        ok = proc.returncode == 0 and dest.is_file()
        return {
            "status": "completed" if ok else "failed",
            "engine": "ocrmypdf",
            "output": str(dest) if dest.is_file() else None,
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "engine": "ocrmypdf", "output": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "engine": "ocrmypdf", "error": str(exc)[:300], "output": None}


def structure_heuristics(text: str, path: Path | None = None) -> dict[str, Any]:
    """Lightweight WCAG/PDF structure signals when veraPDF is unavailable."""
    issues: list[str] = []
    score = 100.0
    if not text or len(text.strip()) < 40:
        issues.append("missing_or_thin_text_layer")
        score -= 40
    if text and not re.search(r"(?m)^.+$", text):
        issues.append("no_line_structure")
        score -= 10
    # Heading-like lines
    headings = len(re.findall(r"(?m)^[A-Z][A-Za-z0-9 /&-]{3,60}$", text[:5000]))
    if text and headings == 0 and len(text) > 400:
        issues.append("no_heading_like_lines")
        score -= 10
    if path and path.suffix.lower() == ".pdf" and (not text or len(text.strip()) < 40):
        issues.append("pdf_likely_scan_without_ocr")
        score -= 15
    score = max(0.0, min(100.0, score))
    return {
        "engine": "heuristic",
        "wcag_score": score,
        "issues": issues,
        "heading_like_lines": headings,
        "note": "heuristic only — not a substitute for veraPDF PDF/UA",
    }


def dual_audience_briefs(
    text: str,
    *,
    doc_kind: str,
    source_label: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    preview = (text or "")[:8000]
    kind = classify_document_kind(preview, doc_kind)
    opener = _DOC_HINTS.get(kind, _DOC_HINTS["general"])

    caregiver = {
        "audience": "caregiver",
        "doc_kind": kind,
        "source": source_label,
        "summary": opener,
        "action_bullets": [
            "Confirm patient identity matches the document.",
            "Note any deadlines, dollar amounts, or follow-up dates.",
            "Flag PHI before sharing outside the local vault.",
        ],
        "text_excerpt": preview[:1500],
        "decision_authority": "prepare_only",
    }
    caregivee = {
        "audience": "caregivee",
        "doc_kind": kind,
        "source": source_label,
        "summary": opener,
        "gentle_bullets": [
            "This is a simplified summary, not medical advice.",
            "Ask your care partner if any date or amount is unclear.",
            "Keep the original paper or PDF in a safe place.",
        ],
        "decision_authority": "prepare_only",
    }

    llm_meta: dict[str, Any] = {"used": False}
    if use_llm and preview.strip():
        try:
            assert_phi_model_safe(AIDA_MODEL)
            import httpx

            prompt = (
                "You are A.I.D.A. (prepare-only). Summarize this caregiver document for two audiences.\n"
                "Return STRICT JSON with keys caregiver_summary (string), caregiver_actions (array of 3 short strings), "
                "caregivee_summary (string, gentle plain language ~6th grade), caregivee_bullets (array of 3 short strings).\n"
                "Do not invent clinical facts. If uncertain, say so.\n\n"
                f"doc_kind={kind}\nsource={source_label or 'unknown'}\n\nDOCUMENT:\n{preview[:6000]}"
            )
            headers = {"Content-Type": "application/json"}
            if LITELLM_KEY:
                headers["Authorization"] = f"Bearer {LITELLM_KEY}"
            payload = {
                "model": AIDA_MODEL,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON. prepare_only, no clinical decisions."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 800,
            }
            with httpx.Client(timeout=90.0) as client:
                r = client.post(f"{LITELLM_BASE}/v1/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                body = r.json()
            content = body["choices"][0]["message"]["content"]
            # strip fences if present
            m = re.search(r"\{[\s\S]*\}", content)
            data = json.loads(m.group(0) if m else content)
            if data.get("caregiver_summary"):
                caregiver["summary"] = str(data["caregiver_summary"])[:2000]
            if isinstance(data.get("caregiver_actions"), list):
                caregiver["action_bullets"] = [str(x)[:200] for x in data["caregiver_actions"][:5]]
            if data.get("caregivee_summary"):
                caregivee["summary"] = str(data["caregivee_summary"])[:2000]
            if isinstance(data.get("caregivee_bullets"), list):
                caregivee["gentle_bullets"] = [str(x)[:200] for x in data["caregivee_bullets"][:5]]
            llm_meta = {"used": True, "model": AIDA_MODEL, "base": LITELLM_BASE}
        except Exception as exc:  # noqa: BLE001
            llm_meta = {"used": False, "error": str(exc)[:300], "model": AIDA_MODEL}

    return {
        "doc_kind": kind,
        "caregiver": caregiver,
        "caregivee": caregivee,
        "llm": llm_meta,
        "decision_authority": "prepare_only",
    }


def write_briefs(dual: dict[str, Any], briefs_dir: Path, stem: str) -> dict[str, str]:
    briefs_dir.mkdir(parents=True, exist_ok=True)
    cg = dual.get("caregiver") or {}
    ce = dual.get("caregivee") or {}

    def _md(title: str, body: dict[str, Any], bullets_key: str) -> str:
        lines = [
            f"# {title}",
            "",
            f"**doc_kind:** {body.get('doc_kind', dual.get('doc_kind', 'general'))}",
            f"**source:** {body.get('source') or stem}",
            f"**authority:** prepare_only",
            f"**generated:** {utc_now()}",
            "",
            "## Summary",
            "",
            str(body.get("summary") or ""),
            "",
            "## Points",
            "",
        ]
        for b in body.get(bullets_key) or []:
            lines.append(f"- {b}")
        lines.append("")
        return "\n".join(lines)

    caregiver_path = briefs_dir / f"{stem}__caregiver.md"
    caregivee_path = briefs_dir / f"{stem}__caregivee.md"
    html_path = briefs_dir / f"{stem}__sr.html"

    caregiver_path.write_text(_md("Caregiver brief (A.I.D.A.)", cg, "action_bullets"), encoding="utf-8")
    caregivee_path.write_text(_md("Plain-language brief (A.I.D.A.)", ce, "gentle_bullets"), encoding="utf-8")

    # Screen-reader friendly linear HTML (VoiceOver / NVDA export for HITL)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>A.I.D.A. accessible brief — {stem}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; font-size: 18px; line-height: 1.5; max-width: 42rem; margin: 1.5rem; }}
    h1,h2 {{ font-weight: 700; }}
  </style>
</head>
<body>
  <header><h1>Accessible document brief</h1>
  <p>Generated by A.I.D.A. (prepare only). HITL screen-reader check: pending.</p></header>
  <main>
    <section aria-labelledby="cg">
      <h2 id="cg">For the caregiver</h2>
      <p>{_esc(cg.get("summary"))}</p>
      <ul>{"".join(f"<li>{_esc(x)}</li>" for x in (cg.get("action_bullets") or []))}</ul>
    </section>
    <section aria-labelledby="ce">
      <h2 id="ce">Plain language</h2>
      <p>{_esc(ce.get("summary"))}</p>
      <ul>{"".join(f"<li>{_esc(x)}</li>" for x in (ce.get("gentle_bullets") or []))}</ul>
    </section>
  </main>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return {
        "caregiver_path": str(caregiver_path),
        "caregivee_path": str(caregivee_path),
        "screen_reader_html": str(html_path),
    }


def _esc(s: Any) -> str:
    t = str(s or "")
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def list_pending(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or ingest_root()
    found: list[dict[str, Any]] = []
    if not base.is_dir():
        return found
    cats = list(CATEGORIES.keys())
    for cat in cats:
        cat_dir = base / cat
        if not cat_dir.is_dir():
            continue
        for d in (cat_dir / "_incoming", cat_dir):
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if not p.is_file() or p.name.startswith("."):
                    continue
                if p.suffix.lower() not in _SCAN_EXTS:
                    continue
                if d.name == cat and p.parent.name != cat:
                    continue
                if p.parent.name not in (cat, "_incoming"):
                    continue
                found.append(
                    {
                        "path": str(p),
                        "category": cat,
                        "rules": CATEGORIES.get(cat, CATEGORIES["_unsorted"]),
                    }
                )
    return found


def _claim(src: Path, category: str, base: Path) -> Path:
    proc = base / category / "_processing"
    proc.mkdir(parents=True, exist_ok=True)
    dest = proc / src.name
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = proc / f"{src.stem}__{stamp}{src.suffix}"
    shutil.move(str(src), str(dest))
    return dest


def _finish(processing: Path, category: str, base: Path, *, ok: bool, error: str | None = None) -> Path:
    dest_dir = base / category / ("_done" if ok else "_error")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / processing.name
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = dest_dir / f"{processing.stem}__{stamp}{processing.suffix}"
    shutil.move(str(processing), str(dest))
    if not ok and error:
        dest.with_suffix(dest.suffix + ".error.json").write_text(
            json.dumps({"error": error, "path": str(dest), "at": utc_now()}, indent=2),
            encoding="utf-8",
        )
    return dest


def process_document(
    file_path: str | Path,
    *,
    category: str | None = None,
    claim: bool = False,
    execute_ocr: bool = True,
    force_ocr: bool = False,
    use_llm: bool = True,
    use_vlm: bool | None = None,
    consent_id: str | None = None,
    wait_stable_s: float = 0.0,
) -> dict[str, Any]:
    """Run full A.I.D.A. prepare-only pass on one file.

    use_vlm: None=env Docling default, True=force GraniteDocling, False=standard only.
    """
    t0 = time.perf_counter()
    src = Path(file_path).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"not found: {src}"}

    if wait_stable_s > 0:
        _wait_stable(src, wait_stable_s)

    base = ingest_root()
    cat = category or _infer_category(src, base) or "_unsorted"
    rules = CATEGORIES.get(cat, CATEGORIES["_unsorted"])
    flow_id = str(uuid.uuid4())
    report_id = flow_id[:12]
    consent = consent_id or CONSENT_DEFAULT

    work = _claim(src, cat, base) if claim else src
    briefs_dir = base / cat / "_briefs"
    prep_dir = base / cat / "_prep"
    reports_dir = base / cat / REPORTS_DIR_NAME
    assured_dir = base / cat / "_done" / "assured" if claim else work.parent / "assured"
    for d in (briefs_dir, prep_dir, reports_dir, assured_dir):
        d.mkdir(parents=True, exist_ok=True)

    file_hash = sha256_file(work)
    ocr_result: dict[str, Any] = {"status": "skipped"}
    work_for_text = work

    # OCR path for PDFs / images
    if execute_ocr and work.suffix.lower() == ".pdf":
        ocr_dest = assured_dir / f"{work.stem}.ocr.pdf"
        ocr_result = run_ocr(work, ocr_dest, force=force_ocr)
        if ocr_result.get("output") and Path(ocr_result["output"]).is_file():
            work_for_text = Path(ocr_result["output"])
    elif execute_ocr and work.suffix.lower() in _IMAGE_EXTS and ocrmypdf_available():
        # image → single-page PDF via Pillow then OCR
        try:
            from PIL import Image

            img_pdf = prep_dir / f"{work.stem}.pdf"
            im = Image.open(work)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(img_pdf, "PDF", resolution=300.0)
            ocr_dest = assured_dir / f"{work.stem}.ocr.pdf"
            ocr_result = run_ocr(img_pdf, ocr_dest, force=True)
            if ocr_result.get("output") and Path(ocr_result["output"]).is_file():
                work_for_text = Path(ocr_result["output"])
        except Exception as exc:  # noqa: BLE001
            ocr_result = {"status": "error", "error": str(exc)[:300], "engine": "image_pdf"}

    extract = extract_text(work_for_text)
    text = extract.get("text") or ""
    doc_kind = classify_document_kind(text, rules.get("doc_kind"))
    phi_flags = initial_phi_flags(text)

    # Docling structure IR (MIT; GraniteDocling Apache-2.0 VLM always selectable)
    docling_dir = prep_dir / "docling"
    docling_result = docling_runner.convert_document(
        work_for_text if work_for_text.is_file() else work,
        out_dir=docling_dir,
        stem=work.stem,
        use_vlm=use_vlm,
    )
    if docling_result.get("status") == "ok" and (docling_result.get("markdown") or "").strip():
        # Prefer Docling markdown for richer structure when extract is thin
        if (extract.get("chars") or len(text)) < 80 or len(docling_result.get("markdown") or "") > len(text) * 0.8:
            text = docling_result["markdown"]
            extract = {
                **extract,
                "engine": f"{extract.get('engine')}+docling",
                "chars": len(text),
                "docling_chars": docling_result.get("markdown_chars"),
            }

    # Accessibility: veraPDF + heuristics + mastery stack
    has_ocr = ocr_result.get("status") == "completed"
    verapdf = run_verapdf(work_for_text if work_for_text.suffix.lower() == ".pdf" else work)
    heur = structure_heuristics(text, work_for_text)
    heur_score = float(heur.get("wcag_score") or 0.0)
    vp_score = verapdf.get("wcag_score")
    if verapdf.get("status") == "ok" and vp_score is not None:
        wcag_score = float(vp_score)
    else:
        wcag_score = heur_score
    if verapdf.get("pdf_ua_pass") is False:
        wcag_score = min(wcag_score, 45.0)

    ada = ada_mastery.ada_pre_check(
        text,
        doc_type="pdf" if work.suffix.lower() == ".pdf" else work.suffix.lower().lstrip(".") or "document",
        has_ocr=has_ocr,
        extract_chars=int(extract.get("chars") or len(text)),
        path=work_for_text,
    )

    dual = dual_audience_briefs(
        text,
        doc_kind=doc_kind,
        source_label=work.name,
        use_llm=use_llm,
    )
    brief_paths = write_briefs(dual, briefs_dir, work.stem)

    # Full linear HTML for axe + VoiceOver (beyond dual brief snippet)
    full_html_path = briefs_dir / f"{work.stem}__document_linear.html"
    html_a11y.write_document_html(
        full_html_path,
        text,
        stem=work.stem,
        caregiver_summary=str((dual.get("caregiver") or {}).get("summary") or ""),
        plain_summary=str((dual.get("caregivee") or {}).get("summary") or ""),
    )
    axe_report = html_a11y.run_axe_on_html(full_html_path)
    contrast = html_a11y.contrast_self_check_html(full_html_path)
    html_bundle = {
        "document_linear_html": str(full_html_path),
        "axe": axe_report,
        "contrast": contrast,
        "status": axe_report.get("status"),
        "violations_count": axe_report.get("violations_count") or 0,
    }

    # JIST + emotional soft gate (local LLM only)
    jist = jist_relay.build_jist(text, doc_kind=doc_kind, dual=dual, use_llm=use_llm)

    mastery = ada_mastery.build_mastery_scorecard(
        text=text,
        verapdf=verapdf,
        heuristic=heur,
        ada=ada,
        html_a11y=html_bundle,
        has_sr_html=True,
        has_jist=True,
        has_ocr=has_ocr,
        path=work_for_text,
    )
    # Prefer composite for primary wcag_score when mastery ran
    if mastery.get("composite_score") is not None:
        wcag_score = float(mastery["composite_score"])

    style_rec = style_packs.recommend_style(text, doc_kind=doc_kind, category=cat)

    accessibility = {
        "wcag_score": wcag_score,
        "composite_score": mastery.get("composite_score"),
        "pdf_ua_pass": verapdf.get("pdf_ua_pass"),
        "verapdf": verapdf,
        "heuristic": heur,
        "ada_pre_check": ada,
        "scorecard": mastery,
        "html_a11y": html_bundle,
        "structure_engine": docling_result.get("engine") if docling_result.get("status") == "ok" else None,
        "docling": {
            "status": docling_result.get("status"),
            "pipeline": docling_result.get("pipeline"),
            "vlm_model": docling_result.get("vlm_model"),
            "vlm_requested": docling_result.get("vlm_requested"),
            "vlm_error": docling_result.get("vlm_error"),
            "vlm_option": docling_result.get("vlm_option"),
            "tables": docling_result.get("tables"),
            "pictures": docling_result.get("pictures"),
            "markdown_chars": docling_result.get("markdown_chars"),
            "paths": docling_result.get("paths"),
            "license": docling_result.get("license"),
            "error": docling_result.get("error") or docling_result.get("reason"),
            "elapsed_ms": docling_result.get("elapsed_ms"),
            "note": docling_result.get("note"),
        },
        "hitl_screen_reader": "pending",
        "issues": list(heur.get("issues") or [])
        + list(verapdf.get("issues") or [])
        + list(ada.get("ada_flags") or []),
    }

    # Four-tier knowledge store
    tier_store.ensure_tier_tree(base)
    tiers: dict[str, Any] = {}
    try:
        tiers["raw"] = tier_store.store_raw(base, work, category=cat, sha256=file_hash)
        proc_src = work_for_text if work_for_text.is_file() else work
        tiers["processed"] = tier_store.store_processed(
            base,
            proc_src,
            category=cat,
            stem=work.stem,
            report_snippet={
                "accessibility": {
                    "wcag_score": wcag_score,
                    "pdf_ua_pass": verapdf.get("pdf_ua_pass"),
                    "composite_score": mastery.get("composite_score"),
                },
                "report_id": report_id,
            },
        )
        # Bare text + pix
        image_notes: list[str] = []
        if work.suffix.lower() in _IMAGE_EXTS:
            image_notes.append(f"Source image: {work.name} (OCR path applied when possible)")
        bare_md = (text or "")[:50000]
        if not bare_md.strip():
            bare_md = str((dual.get("caregivee") or {}).get("summary") or "")
        # Prefer Docling markdown for bare text + pix when available
        if docling_result.get("status") == "ok" and (docling_result.get("markdown") or "").strip():
            bare_md = docling_result["markdown"][:50000]
            if docling_result.get("tables"):
                image_notes.append(f"Docling detected tables: {docling_result.get('tables')}")
            if docling_result.get("pictures"):
                image_notes.append(f"Docling detected pictures/figures: {docling_result.get('pictures')}")
        tiers["txt_pix"] = tier_store.store_txt_pix(
            base,
            category=cat,
            stem=work.stem,
            markdown=bare_md,
            image_notes=image_notes,
        )
        tiers["jist"] = tier_store.store_jist(base, category=cat, stem=work.stem, jist=jist)
    except Exception as exc:  # noqa: BLE001
        tiers["error"] = str(exc)[:300]

    # Safe remediation (PyMuPDF metadata/outline + optional OpenDataLoader tag + re-veraPDF)
    rem_dir = base / cat / "_prep" / "remediation"
    rem = remediation_mod.run_safe_remediation(
        work_for_text if work_for_text.suffix.lower() == ".pdf" else work,
        rem_dir,
        stem=work.stem,
        scorecard=mastery,
        verapdf=verapdf,
        title=work.stem.replace("_", " "),
        revalidate=True,
    )

    # Form-fill candidate detect only (never auto-fill medical ingest)
    form_probe: dict[str, Any] = {"status": "skipped"}
    try:
        pdf_for_form = work_for_text if work_for_text.suffix.lower() == ".pdf" else work
        if pdf_for_form.suffix.lower() == ".pdf":
            raw_probe = form_fill_mod.inspect_acroform(pdf_for_form)
            form_probe = {
                "status": raw_probe.get("status"),
                "form_fill_candidate": bool(raw_probe.get("form_fill_candidate")),
                "field_count": raw_probe.get("field_count") or 0,
                "engine": raw_probe.get("engine"),
                "auto_fill": False,
                "note": "Inspect only on ingest — use POST /v1/forms/fill with HITL",
            }
    except Exception as exc:  # noqa: BLE001
        form_probe = {"status": "error", "error": str(exc)[:200], "auto_fill": False}

    receipt = {
        "status": "ok",
        "agent": "A.I.D.A.",
        "action": "document_first_pass_deep_assurance",
        "execution_phases": ["first_pass", "deep_assurance"],
        "aliases_merged": ["A.I.A.D.A.", "A.C.C.E.S.S."],
        "decision_authority": "prepare_only",
        "report_id": report_id,
        "flow_id": flow_id,
        "category": cat,
        "rules": rules,
        "consent_id": consent,
        "source": {
            "path": str(work),
            "original_name": src.name if not claim else work.name,
            "sha256": file_hash,
            "suffix": work.suffix.lower(),
            "bytes": work.stat().st_size,
        },
        "ocr": ocr_result,
        "extract": {
            "engine": extract.get("engine"),
            "pages": extract.get("pages"),
            "chars": extract.get("chars") or len(text),
            "error": extract.get("error"),
            "text_path_used": str(work_for_text),
        },
        "doc_kind": doc_kind,
        "phi_initial_flags": phi_flags,
        "accessibility": accessibility,
        "mastery": mastery,
        "dual_audience": {
            "doc_kind": dual.get("doc_kind"),
            "llm": dual.get("llm"),
            "caregiver_summary": (dual.get("caregiver") or {}).get("summary"),
            "caregivee_summary": (dual.get("caregivee") or {}).get("summary"),
        },
        "jist": {
            "summary": jist.get("summary"),
            "emotional_risk_level": jist.get("emotional_risk_level"),
            "share_gate": jist.get("share_gate"),
            "hitl_status": jist.get("hitl_status"),
            "llm": jist.get("llm"),
        },
        "style_recommendation": style_rec,
        "structure_ir": {
            "engine": "docling" if docling_result.get("status") == "ok" else docling_result.get("status"),
            "docling": accessibility.get("docling"),
            "vlm_requested": docling_result.get("vlm_requested"),
            "vlm_error": docling_result.get("vlm_error"),
        },
        "form_fill": form_probe,
        "tiers": tiers,
        "remediation": {
            "status": rem.get("status"),
            "plan_path": rem.get("plan_path"),
            "remediated_path": rem.get("remediated_path"),
            "tagged_path": rem.get("tagged_path"),
            "pymupdf_remediation": rem.get("pymupdf_remediation"),
            "metadata_remediation": rem.get("metadata_remediation"),
            "opendataloader_tagging": rem.get("opendataloader_tagging"),
            "verapdf_before": rem.get("verapdf_before"),
            "verapdf_after": rem.get("verapdf_after"),
            "verapdf_after_tagged": rem.get("verapdf_after_tagged"),
            "delta": rem.get("delta"),
            "delta_path": rem.get("delta_path"),
            "hitl_required": True,
        },
        "brief_paths": {
            **brief_paths,
            "document_linear_html": str(full_html_path),
        },
        "downstream": ["K.A.R.E.N.", "E.T.H.I.C.S.", "J.E.S.U.S."],
        "model_policy": {
            "model": AIDA_MODEL,
            "allow_remote": AIDA_ALLOW_REMOTE,
            "litellm_base": LITELLM_BASE,
        },
        "timestamp": utc_now(),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

    # VPAT seed (needs receipt fields)
    try:
        vpat_paths = vpat_export.write_vpat(receipt, base / cat / "_aida_reports", work.stem)
        receipt["vpat"] = vpat_paths
        brief_paths_ext = dict(receipt["brief_paths"])
        brief_paths_ext.update(vpat_paths)
        receipt["brief_paths"] = brief_paths_ext
    except Exception as exc:  # noqa: BLE001
        receipt["vpat"] = {"error": str(exc)[:200]}

    # Catalog
    try:
        a11y_catalog.upsert_resource(
            title=work.stem,
            source=str(work),
            rtype=work.suffix.lower().lstrip(".") or "file",
            category=cat,
            wcag_score=wcag_score,
            composite_score=mastery.get("composite_score"),
            pdf_ua_pass=verapdf.get("pdf_ua_pass"),
            issues=accessibility.get("issues"),
            remediation_status=str(rem.get("status") or "pending"),
            hitl_screen_reader="pending",
            report_id=report_id,
            context=doc_kind,
            db_path=a11y_catalog.default_db_path(base),
        )
        receipt["catalog"] = {"status": "ok", "db": str(a11y_catalog.default_db_path(base))}
    except Exception as exc:  # noqa: BLE001
        receipt["catalog"] = {"status": "error", "error": str(exc)[:200]}

    report_path = reports_dir / f"{work.stem}__{report_id}.json"
    report_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt["report_path"] = str(report_path)

    if claim:
        final = _finish(work, cat, base, ok=True)
        receipt["source"]["final_path"] = str(final)
        try:
            shutil.copy2(report_path, base / cat / "_done" / report_path.name)
        except OSError:
            pass

    return receipt


def _infer_category(path: Path, base: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(base.resolve())
    except ValueError:
        return None
    if not rel.parts:
        return None
    name = rel.parts[0]
    if name in CATEGORIES:
        return name
    return None


def _wait_stable(path: Path, seconds: float) -> None:
    """Wait until file size is stable (scanner partial writes)."""
    deadline = time.time() + max(seconds, 0.5)
    last = -1
    while time.time() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            time.sleep(0.2)
            continue
        if size == last and size > 0:
            return
        last = size
        time.sleep(0.3)


def process_watch_tick(
    *,
    limit: int = 20,
    execute_ocr: bool = True,
    use_llm: bool = True,
    wait_stable_s: float = 1.5,
) -> dict[str, Any]:
    ensure_drop_tree()
    pending = list_pending()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in pending[:limit]:
        try:
            r = process_document(
                item["path"],
                category=item["category"],
                claim=True,
                execute_ocr=execute_ocr,
                use_llm=use_llm,
                wait_stable_s=wait_stable_s,
            )
            results.append(r)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": item["path"], "error": str(exc)[:400]})
            try:
                base = ingest_root()
                cat = item["category"]
                src = Path(item["path"])
                if src.is_file():
                    work = _claim(src, cat, base) if src.parent.name != "_processing" else src
                    _finish(work, cat, base, ok=False, error=str(exc)[:400])
            except Exception:  # noqa: BLE001
                pass
    return {
        "status": "ok",
        "pending_seen": len(pending),
        "processed": len(results),
        "errors": errors,
        "results": results,
    }


def health_snapshot() -> dict[str, Any]:
    from verapdf_runner import verapdf_status

    root = ingest_root()
    model_ok = True
    model_err = None
    try:
        assert_phi_model_safe(AIDA_MODEL)
    except ValueError as exc:
        model_ok = False
        model_err = str(exc)

    litellm_ok = False
    try:
        import httpx

        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{LITELLM_BASE}/health/liveliness")
            litellm_ok = r.status_code == 200
    except Exception:  # noqa: BLE001
        litellm_ok = False

    return {
        "status": "ok",
        "agent": "A.I.D.A.",
        "aliases_merged": ["A.I.A.D.A.", "A.C.C.E.S.S."],
        "execution_phases": ["first_pass", "deep_assurance"],
        "ingest_root": str(root),
        "ingest_root_exists": root.is_dir(),
        "ocrmypdf": ocrmypdf_available(),
        "verapdf": verapdf_status(),
        "axe": html_a11y.axe_available(),
        "catalog_db": str(a11y_catalog.default_db_path(root)),
        "knowledgebase": str(tier_store.knowledgebase_root(root)),
        "docling": docling_runner.docling_available(),
        "style_packs": style_packs.list_pack_ids(),
        "form_fill": form_fill_mod.formfill_available(),
        "opendataloader": odl_runner.opendataloader_available(),
        "adeu": adeu_runner.adeu_available(),
        "officecli": officecli_runner.officecli_available(),
        "document_output": {
            "available": True,
            "endpoints": [
                "POST /v1/document-output/plan",
                "POST /v1/document-output/run",
            ],
            "chain": [
                "style_recommendation",
                "kind_resolve",
                "officecli_generate",
                "adeu_redline_optional",
                "aida_a11y_optional",
            ],
            "manager_role": "document_output_orchestrator",
            "decision_authority": "prepare_only",
        },
        "mastery_tools": [
            "verapdf_pdf_ua",
            "docling_structure_ir",
            "granite_docling_vlm_always_available",
            "opendataloader_tagged_pdf_candidate",
            "form_fill_acroform",
            "adeu_docx_redline",
            "officecli_generate",
            "document_output_orchestrator",
            "structure_heuristics",
            "ada_pre_check",
            "wcag_pdf_techniques_map",
            "section_508_matrix",
            "axe_core_html",
            "contrast_self_check",
            "dual_briefs",
            "jist_emotional_gate",
            "four_tier_store",
            "remediation_plan_metadata",
            "vpat_seed",
            "hitl_screen_reader",
            "resource_catalog",
            "style_recommendation",
        ],
        "model": AIDA_MODEL,
        "model_phi_safe": model_ok,
        "model_error": model_err,
        "litellm_base": LITELLM_BASE,
        "litellm_reachable": litellm_ok,
        "allow_remote": AIDA_ALLOW_REMOTE,
        "consent_default": CONSENT_DEFAULT,
        "decision_authority": "prepare_only",
        "not_included": [
            "wave_saas",
            "jaws_nvda_automation",
            "adobe_acrobat_cli",
            "adobe_auto_tag",
            "grackle",
            "extend_ai",
            "remote_cloud_models_default",
            "pdfix_commercial_default",
        ],
        "open_source_policy": {
            "docling": "MIT",
            "granite_docling": "Apache-2.0 always-available VLM option",
            "opendataloader_pdf": "Apache-2.0 free Tagged PDF candidate; PDF/UA export enterprise_not_used",
            "ai_pdf_autofiller": "MIT form fill",
            "adeu": "MIT DOCX Track Changes redline",
            "officecli": "CLI generate PPTX/DOCX/XLSX external→LiteLLM; hosted off by default",
            "verapdf": "host CLI preferred",
            "adobe": "excluded",
            "pdfix_commercial_default": "excluded",
            "tagging_doctrine": (
                "No mature OSS Acrobat Auto-Tag. Docling infers; "
                "PDFBox-class can write tags (future StructWriter); "
                "veraPDF judges; OpenDataLoader is optional candidate."
            ),
        },
    }


def find_report_file(report_id: str) -> Path | None:
    root = ingest_root()
    if not root.is_dir():
        return None
    matches: list[Path] = []
    for p in root.rglob(f"*{report_id}*.json"):
        if "_aida_reports" in p.parts or p.name.endswith(f"__{report_id}.json"):
            matches.append(p)
    if not matches:
        for p in root.rglob(f"*__{report_id}.json"):
            matches.append(p)
    if not matches:
        return None
    return sorted(matches, key=lambda x: x.stat().st_mtime, reverse=True)[0]


def update_hitl(
    report_id: str,
    *,
    hitl_screen_reader: str | None = None,
    remediation_status: str | None = None,
    notes: str = "",
    actor: str = "admin",
) -> dict[str, Any]:
    """Update HITL fields on a stored report + catalog."""
    path = find_report_file(report_id)
    if not path:
        raise FileNotFoundError(f"no report for {report_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    acc = data.setdefault("accessibility", {})
    if hitl_screen_reader is not None:
        allowed = {"pending", "pass", "fail", "partial"}
        if hitl_screen_reader not in allowed:
            raise ValueError(f"hitl_screen_reader must be one of {sorted(allowed)}")
        acc["hitl_screen_reader"] = hitl_screen_reader
        a11y_catalog.log_hitl(
            report_id,
            field="hitl_screen_reader",
            value=hitl_screen_reader,
            notes=notes,
            actor=actor,
            db_path=a11y_catalog.default_db_path(ingest_root()),
        )
    if remediation_status is not None:
        rem = data.setdefault("remediation", {})
        rem["status"] = remediation_status
        rem["hitl_notes"] = notes
        rem["hitl_actor"] = actor
        rem["hitl_at"] = utc_now()
        a11y_catalog.log_hitl(
            report_id,
            field="remediation_status",
            value=remediation_status,
            notes=notes,
            actor=actor,
            db_path=a11y_catalog.default_db_path(ingest_root()),
        )
    data["hitl_updated_at"] = utc_now()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # refresh VPAT seed if present
    try:
        stem = path.name.split("__")[0]
        cat = data.get("category") or "_unsorted"
        vpat_paths = vpat_export.write_vpat(data, ingest_root() / cat / "_aida_reports", stem)
        data["vpat"] = vpat_paths
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    data["_report_file"] = str(path)
    return data
