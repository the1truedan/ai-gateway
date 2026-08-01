#!/usr/bin/env python3
"""AcroForm PDF fill client for A.I.D.A. — Phase 2.

Wraps ai-pdf-autofiller (MIT) over HTTP, or optional in-process SDK.
Deterministic aliases first; semantic AI inference **default OFF** (PHI-safe).
Prepare-only: filled PDFs are never submit_ready without HITL.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

FORMFILL_URL = os.environ.get("AIDA_FORMFILL_URL", "http://localhost:8793").rstrip("/")
FORMFILL_DISABLE = os.environ.get("AIDA_FORMFILL_DISABLE", "0") == "1"
FORMFILL_TIMEOUT = float(os.environ.get("AIDA_FORMFILL_TIMEOUT", "60"))
FORMFILL_API_KEY = os.environ.get("AIDA_FORMFILL_API_KEY", "").strip()

RECIPES = [
    {
        "id": "w9",
        "title": "IRS W-9",
        "notes": "Alias pack in ai-pdf-autofiller recipes/w9.md",
        "sample_keys": ["name", "business_name", "tin", "address", "city", "state", "zip"],
    },
    {
        "id": "hr-onboarding",
        "title": "HR onboarding / employee intake",
        "notes": "recipes/hr-onboarding.md",
        "sample_keys": ["firstname", "lastname", "dob", "email", "ssn"],
    },
    {
        "id": "generic",
        "title": "Generic AcroForm",
        "notes": "Pass field-ish keys; aliases normalize firstname/txtFName/etc.",
        "sample_keys": ["firstname", "lastname", "dob", "email", "phone", "address"],
    },
]


def formfill_available() -> dict[str, Any]:
    if FORMFILL_DISABLE:
        return {
            "available": False,
            "reason": "AIDA_FORMFILL_DISABLE=1",
            "base_url": FORMFILL_URL,
            "mode": "disabled",
        }
    # Prefer HTTP sidecar health
    try:
        import httpx

        headers = _headers()
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{FORMFILL_URL}/health", headers=headers)
            if r.status_code == 200:
                body: dict[str, Any] = {}
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    body = {"raw": r.text[:200]}
                return {
                    "available": True,
                    "base_url": FORMFILL_URL,
                    "mode": "http_sidecar",
                    "sidecar": body,
                    "semantic_inference_default": False,
                    "license": "MIT (ai-pdf-autofiller)",
                    "submit_ready_default": False,
                }
            return {
                "available": False,
                "base_url": FORMFILL_URL,
                "mode": "http_sidecar",
                "reason": f"health HTTP {r.status_code}",
                "hint": "Run ./scripts/aida_setup_formfill.sh",
            }
    except Exception as exc:  # noqa: BLE001
        # Optional in-process SDK
        try:
            import pdf_autofiller  # noqa: F401

            return {
                "available": True,
                "base_url": None,
                "mode": "in_process_sdk",
                "package": "pdf_autofiller",
                "semantic_inference_default": False,
                "license": "MIT",
                "submit_ready_default": False,
                "note": f"sidecar unreachable ({exc}); using local SDK",
            }
        except ImportError:
            return {
                "available": False,
                "base_url": FORMFILL_URL,
                "mode": "none",
                "reason": f"sidecar unreachable: {exc}",
                "hint": (
                    "docker run --rm -p 8793:8000 -e API_AUTH_ENABLED=false "
                    "ghcr.io/lindseystead/ai-pdf-autofiller:latest"
                    "  # or ./scripts/aida_setup_formfill.sh"
                ),
            }


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if FORMFILL_API_KEY:
        h["X-API-Key"] = FORMFILL_API_KEY
    return h


def list_recipes() -> list[dict[str, Any]]:
    return list(RECIPES)


def inspect_acroform(pdf_path: str | Path) -> dict[str, Any]:
    """List AcroForm field names (local, no sidecar required)."""
    src = Path(pdf_path).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"not found: {src}"}
    if src.suffix.lower() != ".pdf":
        return {"status": "error", "error": "not a PDF"}

    fields: list[dict[str, Any]] = []
    engine = "none"
    # Prefer pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(src))
        engine = "pypdf"
        raw = reader.get_fields() or {}
        for name, meta in raw.items():
            if name is None:
                continue
            entry: dict[str, Any] = {"name": str(name)}
            if isinstance(meta, dict):
                ft = meta.get("/FT") or meta.get("FT")
                if ft is not None:
                    entry["type"] = str(ft)
                val = meta.get("/V") or meta.get("V")
                if val is not None:
                    entry["value"] = str(val)[:200]
            fields.append(entry)
        return {
            "status": "ok",
            "engine": engine,
            "path": str(src),
            "field_count": len(fields),
            "fields": fields,
            "form_fill_candidate": len(fields) > 0,
        }
    except Exception as pypdf_exc:  # noqa: BLE001
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(src))
            engine = "pymupdf"
            for page in doc:
                for w in page.widgets() or []:
                    fields.append(
                        {
                            "name": w.field_name or "",
                            "type": str(w.field_type_string or w.field_type),
                            "value": (w.field_value or "")[:200]
                            if w.field_value is not None
                            else "",
                        }
                    )
            doc.close()
            # de-dupe by name
            seen: set[str] = set()
            uniq: list[dict[str, Any]] = []
            for f in fields:
                n = f.get("name") or ""
                if n in seen:
                    continue
                seen.add(n)
                uniq.append(f)
            return {
                "status": "ok",
                "engine": engine,
                "path": str(src),
                "field_count": len(uniq),
                "fields": uniq,
                "form_fill_candidate": len(uniq) > 0,
                "pypdf_error": str(pypdf_exc)[:120],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "error": f"pypdf:{pypdf_exc}; pymupdf:{exc}"[:400],
                "path": str(src),
            }


def fill_pdf(
    pdf_path: str | Path,
    user_data: dict[str, Any],
    *,
    out_path: str | Path | None = None,
    strict: bool = True,
    use_semantic_inference: bool = False,
    allow_fallback_mapping: bool = False,
) -> dict[str, Any]:
    """Fill AcroForm PDF from user_data JSON. Returns paths + report."""
    t0 = time.perf_counter()
    src = Path(pdf_path).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"not found: {src}"}
    if not isinstance(user_data, dict):
        return {"status": "error", "error": "user_data must be a JSON object"}

    dest = (
        Path(out_path).expanduser().resolve()
        if out_path
        else src.parent / f"{src.stem}.filled.pdf"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)

    avail = formfill_available()
    if not avail.get("available"):
        return {
            "status": "unavailable",
            "error": avail.get("reason"),
            "hint": avail.get("hint"),
            "form_fill": avail,
            "submit_ready": False,
            "hitl_required": True,
        }

    mode = avail.get("mode")
    if mode == "http_sidecar":
        result = _fill_http(
            src,
            dest,
            user_data,
            strict=strict,
            use_semantic_inference=use_semantic_inference,
            allow_fallback_mapping=allow_fallback_mapping,
        )
    elif mode == "in_process_sdk":
        result = _fill_sdk(
            src,
            dest,
            user_data,
            strict=strict,
        )
    else:
        return {
            "status": "unavailable",
            "error": "no form-fill backend",
            "form_fill": avail,
            "submit_ready": False,
            "hitl_required": True,
        }

    result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["submit_ready"] = False
    result["hitl_required"] = True
    result["decision_authority"] = "prepare_only"
    result["semantic_inference"] = bool(use_semantic_inference)
    result["note"] = (
        "Filled PDF is prepare-only. Review fields (HITL) before any tax/gov submit. "
        "Semantic AI default off for PHI safety."
    )
    # Write report sidecar
    report_path = dest.with_suffix(".fill_report.json")
    try:
        report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_path"] = str(report_path)
    except OSError:
        pass
    return result


def _fill_http(
    src: Path,
    dest: Path,
    user_data: dict[str, Any],
    *,
    strict: bool,
    use_semantic_inference: bool,
    allow_fallback_mapping: bool,
) -> dict[str, Any]:
    import httpx

    headers = _headers()
    data = {
        "user_data": json.dumps(user_data),
        "strict": "true" if strict else "false",
        "use_semantic_inference": "true" if use_semantic_inference else "false",
        "allow_fallback_mapping": "true" if allow_fallback_mapping else "false",
    }
    try:
        with httpx.Client(timeout=FORMFILL_TIMEOUT) as client:
            with src.open("rb") as f:
                files = {"pdf_file": (src.name, f, "application/pdf")}
                r = client.post(
                    f"{FORMFILL_URL}/fill",
                    data=data,
                    files=files,
                    headers=headers,
                )
        if r.status_code != 200:
            detail: Any
            try:
                detail = r.json()
            except Exception:  # noqa: BLE001
                detail = r.text[:500]
            return {
                "status": "error",
                "engine": "ai-pdf-autofiller-http",
                "http_status": r.status_code,
                "error": detail,
                "base_url": FORMFILL_URL,
            }
        dest.write_bytes(r.content)
        return {
            "status": "ok",
            "engine": "ai-pdf-autofiller-http",
            "base_url": FORMFILL_URL,
            "source": str(src),
            "output": str(dest),
            "bytes": dest.stat().st_size,
            "fields_written": r.headers.get("X-PDF-Fields-Written"),
            "fields_skipped_review": r.headers.get("X-PDF-Fields-Skipped-Review"),
            "fields_skipped_empty": r.headers.get("X-PDF-Fields-Skipped-Empty"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "engine": "ai-pdf-autofiller-http",
            "error": str(exc)[:400],
            "base_url": FORMFILL_URL,
        }


def _fill_sdk(
    src: Path,
    dest: Path,
    user_data: dict[str, Any],
    *,
    strict: bool,
) -> dict[str, Any]:
    try:
        from pdf_autofiller import fill

        fill(str(src), user_data, str(dest))
        return {
            "status": "ok",
            "engine": "pdf_autofiller_sdk",
            "source": str(src),
            "output": str(dest),
            "bytes": dest.stat().st_size if dest.is_file() else 0,
            "strict": strict,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "engine": "pdf_autofiller_sdk",
            "error": str(exc)[:400],
        }
