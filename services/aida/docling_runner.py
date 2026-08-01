#!/usr/bin/env python3
"""Docling structure IR for A.I.D.A. — MIT open source, local, Adobe-free.

Default: standard DocumentConverter pipeline (layout, tables, reading order).
GraniteDocling VLM (Apache-2.0, ibm-granite/granite-docling-258M) is **always
available as an option** when Docling is installed — enable via:
  - env AIDA_DOCLING_VLM=1 or AIDA_DOCLING_PIPELINE=vlm (process default)
  - per-request use_vlm=True on convert / ingest

Does NOT claim PDF/UA write-back. Produces Markdown + JSON IR for tiers,
txt_pix enrichment, and downstream style/form agents. Re-validate PDFs
with veraPDF separately.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DOCLING_DISABLE = os.environ.get("AIDA_DOCLING_DISABLE", "0") == "1"
# standard | vlm  — process default only; request can override
DOCLING_PIPELINE = os.environ.get("AIDA_DOCLING_PIPELINE", "standard").strip().lower()
DOCLING_VLM = os.environ.get("AIDA_DOCLING_VLM", "0") == "1"
DOCLING_VLM_MODEL = os.environ.get(
    "AIDA_DOCLING_VLM_MODEL", "granite_docling"
).strip()
DOCLING_TIMEOUT_NOTE = (
    "First Docling run may download models; GraniteDocling VLM is larger (Apache-2.0)."
)


def env_wants_vlm() -> bool:
    return DOCLING_VLM or DOCLING_PIPELINE == "vlm"


def docling_available() -> dict[str, Any]:
    """Health/status: always advertise Granite option when Docling imports."""
    base_license = {
        "docling_code": "MIT",
        "granite_docling": "Apache-2.0 (optional VLM weights)",
        "adobe": "not used",
    }
    if DOCLING_DISABLE:
        return {
            "available": False,
            "reason": "AIDA_DOCLING_DISABLE=1",
            "license": base_license,
            "vlm_option": {
                "available": False,
                "reason": "docling disabled",
                "model": DOCLING_VLM_MODEL,
                "license": "Apache-2.0",
            },
        }
    try:
        import docling  # noqa: F401
        from docling.document_converter import DocumentConverter  # noqa: F401

        active = "vlm" if env_wants_vlm() else "standard"
        return {
            "available": True,
            "package": "docling",
            "pipeline_default": active,
            "pipeline": active,  # back-compat
            "vlm_enabled": active == "vlm",
            "vlm_model": DOCLING_VLM_MODEL if active == "vlm" else None,
            "vlm_option": {
                "available": True,
                "model": DOCLING_VLM_MODEL,
                "license": "Apache-2.0",
                "enable": (
                    "AIDA_DOCLING_VLM=1 | AIDA_DOCLING_PIPELINE=vlm | "
                    "request use_vlm=true"
                ),
                "note": (
                    "Always selectable when Docling is installed; "
                    "not forced on every ingest (RAM/time)."
                ),
            },
            "active_pipeline": active,
            "license": base_license,
            "note": DOCLING_TIMEOUT_NOTE,
        }
    except ImportError as exc:
        return {
            "available": False,
            "reason": f"docling not installed: {exc}",
            "hint": "pip install docling  # in services/aida/.venv",
            "license": base_license,
            "vlm_option": {
                "available": False,
                "reason": "docling not installed",
                "model": DOCLING_VLM_MODEL,
                "license": "Apache-2.0",
            },
        }


def _build_standard_converter():
    from docling.document_converter import DocumentConverter

    return DocumentConverter(), "standard", None


def _build_vlm_converter() -> tuple[Any, str, str | None, str | None]:
    """Return (converter, mode, model, error). Soft-fallback to standard on failure."""
    from docling.document_converter import DocumentConverter

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption
    except Exception as exc:  # noqa: BLE001
        conv, mode, model = _build_standard_converter()
        return conv, "standard_fallback_from_vlm", None, f"import_format_options:{exc}"

    # Prefer VlmPipeline when present
    try:
        from docling.pipeline.vlm_pipeline import VlmPipeline

        kwargs: dict[str, Any] = {"pipeline_cls": VlmPipeline}
        # Attach VLM options when API supports it
        try:
            from docling.datamodel.pipeline_options import VlmPipelineOptions

            vlm_opts = VlmPipelineOptions(enable_remote_services=False)
            # Best-effort model name assignment across Docling versions
            for attr in ("model", "vlm_model", "model_name"):
                if hasattr(vlm_opts, attr):
                    try:
                        setattr(vlm_opts, attr, DOCLING_VLM_MODEL)
                    except Exception:  # noqa: BLE001
                        pass
            if hasattr(PdfFormatOption, "__init__"):
                try:
                    fmt = PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=vlm_opts)
                    converter = DocumentConverter(
                        format_options={InputFormat.PDF: fmt}
                    )
                    return converter, "vlm", DOCLING_VLM_MODEL, None
                except TypeError:
                    pass
        except Exception:  # noqa: BLE001
            pass

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_cls=VlmPipeline)
            }
        )
        return converter, "vlm", DOCLING_VLM_MODEL, None
    except Exception as exc:  # noqa: BLE001
        conv, mode, model = _build_standard_converter()
        return conv, "standard_fallback_from_vlm", None, f"vlm_pipeline:{exc}"[:300]


def _build_converter(*, use_vlm: bool | None = None):
    """Build DocumentConverter — standard or GraniteDocling VLM.

    use_vlm:
      None  → env default (AIDA_DOCLING_VLM / AIDA_DOCLING_PIPELINE)
      True  → force VLM attempt
      False → force standard
    """
    want = env_wants_vlm() if use_vlm is None else bool(use_vlm)
    if not want:
        conv, mode, model = _build_standard_converter()
        return conv, mode, model, None
    return _build_vlm_converter()


def convert_document(
    path: str | Path,
    *,
    out_dir: Path | None = None,
    stem: str | None = None,
    use_vlm: bool | None = None,
) -> dict[str, Any]:
    """Run Docling on a local file; write markdown + json IR when out_dir set.

    use_vlm: None=env default, True=force Granite path, False=standard only.
    """
    t0 = time.perf_counter()
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"not found: {src}", "engine": "docling"}

    avail = docling_available()
    if not avail.get("available"):
        return {
            "status": "unavailable",
            "engine": "docling",
            "reason": avail.get("reason"),
            "hint": avail.get("hint"),
            "vlm_option": avail.get("vlm_option"),
        }

    vlm_error: str | None = None
    try:
        converter, pipeline_mode, vlm_model, vlm_error = _build_converter(use_vlm=use_vlm)
        # If VLM was requested but fell back, still try convert; if convert fails
        # on a broken VLM converter, retry standard once.
        try:
            result = converter.convert(str(src))
        except Exception as convert_exc:  # noqa: BLE001
            if pipeline_mode.startswith("vlm") or pipeline_mode == "standard_fallback_from_vlm":
                # Already fallback or VLM failed mid-convert — force standard
                converter, pipeline_mode, vlm_model, _ = _build_converter(use_vlm=False)
                pipeline_mode = "standard_after_vlm_convert_error"
                vlm_error = (vlm_error or "") + f"; convert:{convert_exc}"[:200]
                result = converter.convert(str(src))
            else:
                raise
        doc = result.document

        md = ""
        try:
            md = doc.export_to_markdown() or ""
        except Exception as exc:  # noqa: BLE001
            md = f"(markdown export failed: {exc})"

        structure: Any = None
        try:
            if hasattr(doc, "export_to_dict"):
                structure = doc.export_to_dict()
            elif hasattr(doc, "model_dump"):
                structure = doc.model_dump()
            else:
                structure = {"markdown_chars": len(md)}
        except Exception as exc:  # noqa: BLE001
            structure = {"export_error": str(exc)[:200], "markdown_chars": len(md)}

        tables = 0
        pictures = 0
        try:
            if isinstance(structure, dict):
                tables = len(structure.get("tables") or [])
                pictures = len(
                    structure.get("pictures") or structure.get("figures") or []
                )
            if hasattr(doc, "tables"):
                tables = max(tables, len(doc.tables or []))
            if hasattr(doc, "pictures"):
                pictures = max(pictures, len(doc.pictures or []))
        except Exception:  # noqa: BLE001
            pass

        out_paths: dict[str, str] = {}
        if out_dir is not None:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            s = stem or src.stem
            md_path = out_dir / f"{s}.docling.md"
            json_path = out_dir / f"{s}.docling.json"
            md_path.write_text(md, encoding="utf-8")
            json_path.write_text(
                json.dumps(
                    {
                        "source": str(src),
                        "pipeline": pipeline_mode,
                        "vlm_model": vlm_model,
                        "vlm_error": vlm_error,
                        "markdown_chars": len(md),
                        "tables": tables,
                        "pictures": pictures,
                        "document": structure
                        if _json_size_ok(structure)
                        else {"truncated": True, "markdown_chars": len(md)},
                    },
                    indent=2,
                    default=str,
                )[:2_000_000],
                encoding="utf-8",
            )
            out_paths = {"markdown": str(md_path), "json": str(json_path)}

        out: dict[str, Any] = {
            "status": "ok",
            "engine": "docling",
            "pipeline": pipeline_mode,
            "vlm_model": vlm_model,
            "vlm_requested": env_wants_vlm() if use_vlm is None else bool(use_vlm),
            "vlm_error": vlm_error,
            "vlm_option": avail.get("vlm_option"),
            "license": avail.get("license"),
            "source": str(src),
            "markdown": md[:50000],
            "markdown_chars": len(md),
            "tables": tables,
            "pictures": pictures,
            "paths": out_paths,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "note": (
                "Structure IR only — not a PDF/UA tag write-back. "
                "Validate PDF exports with veraPDF. Adobe not used."
            ),
        }
        return out
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "engine": "docling",
            "error": str(exc)[:500],
            "vlm_error": vlm_error,
            "vlm_option": avail.get("vlm_option"),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        }


def _json_size_ok(obj: Any, limit: int = 400_000) -> bool:
    try:
        return len(json.dumps(obj, default=str)) < limit
    except Exception:  # noqa: BLE001
        return False
