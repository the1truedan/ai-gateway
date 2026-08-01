#!/usr/bin/env python3
"""OfficeCLI generation bridge for A.I.D.A. — Phase 4.

Wraps https://github.com/officecli/officecli for future M.A.N.A.G.E.R. document
output orchestration: PPTX / DOCX / XLSX / report from prompts.

Policy:
  - Prefer External Mode → local LiteLLM (PHI-safe when model is local).
  - Hosted trial / platform publish **off by default** (AIDA_OFFICECLI_ALLOW_HOSTED=0).
  - Medical/PHI categories refuse hosted and refuse remote models when AIDA_ALLOW_REMOTE=0.
  - Always --no-publish for prepare-only local artifacts.
  - HITL / submit_ready false — generation is prepare-only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

OFFICECLI_DISABLE = os.environ.get("AIDA_OFFICECLI_DISABLE", "0") == "1"
OFFICECLI_CMD = os.environ.get("AIDA_OFFICECLI_CMD", "").strip()
OFFICECLI_TIMEOUT = float(os.environ.get("AIDA_OFFICECLI_TIMEOUT", "300"))
ALLOW_HOSTED = os.environ.get("AIDA_OFFICECLI_ALLOW_HOSTED", "0") == "1"
ALLOW_REMOTE = os.environ.get("AIDA_ALLOW_REMOTE", "0") == "1"
LITELLM_BASE = os.environ.get("AIDA_LITELLM_BASE", "http://localhost:4000").rstrip("/")
LITELLM_KEY = (
    os.environ.get("AIDA_LITELLM_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or ""
).strip()
OFFICECLI_MODEL = os.environ.get("AIDA_OFFICECLI_MODEL", "role-phi-local").strip()
PHI_CATEGORIES = {
    "medical",
    "insurance",
    "legal",
    "benefits",
    "records",
    "hipaa",
}

KIND_EXTS = {
    "pptx": ".pptx",
    "docx": ".docx",
    "xlsx": ".xlsx",
    "report": ".html",
    "img": ".png",
    "gif": ".gif",
}


def _config_path() -> Path:
    override = os.environ.get("AIDA_OFFICECLI_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    # macOS Application Support (officecli default)
    mac = Path.home() / "Library" / "Application Support" / "officecli" / "config.json"
    if mac.parent.is_dir() or True:
        return mac
    return Path.home() / ".config" / "officecli" / "config.json"


def _find_bin() -> str | None:
    if OFFICECLI_CMD and Path(OFFICECLI_CMD).is_file():
        return OFFICECLI_CMD
    which = shutil.which("officecli")
    if which:
        return which
    for cand in (
        Path.home() / ".local" / "bin" / "officecli",
        Path("/usr/local/bin/officecli"),
        Path("/opt/homebrew/bin/officecli"),
    ):
        if cand.is_file():
            return str(cand)
    return None


def ensure_external_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    """Write/merge officecli config for External Mode + local LiteLLM."""
    cfg_path = _config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    base = (base_url or LITELLM_BASE).rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    key = api_key if api_key is not None else (LITELLM_KEY or "sk-local")
    mdl = model or OFFICECLI_MODEL

    cfg = {
        "defaults": {
            **(existing.get("defaults") or {}),
            "output_dir": (existing.get("defaults") or {}).get("output_dir") or "./output",
            "mode": (existing.get("defaults") or {}).get("mode") or "fast",
            "publish": bool(publish),
            "pptx_style_preset": (existing.get("defaults") or {}).get(
                "pptx_style_preset", "tech-contrast"
            ),
        },
        "runtime": {"mode": "external"},
        "llm": {
            "provider": "openai",
            "base_url": base,
            "api_key": key,
            "model": mdl,
            "image_model": mdl,
            "review_model": mdl,
            "timeout_sec": int(min(max(OFFICECLI_TIMEOUT, 60), 600)),
        },
        "license": {
            **(existing.get("license") or {}),
            "enabled": False if not ALLOW_HOSTED else (existing.get("license") or {}).get(
                "enabled", False
            ),
        },
        "publish": {
            **(existing.get("publish") or {}),
            "enabled": bool(publish),
        },
    }
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    # Never return full api_key in health
    safe = json.loads(json.dumps(cfg))
    if safe.get("llm", {}).get("api_key"):
        safe["llm"]["api_key"] = "***"
    return {"status": "ok", "path": str(cfg_path), "config": safe}


def officecli_available() -> dict[str, Any]:
    if OFFICECLI_DISABLE:
        return {
            "available": False,
            "reason": "AIDA_OFFICECLI_DISABLE=1",
            "policy": _policy_note(),
        }
    bin_path = _find_bin()
    if not bin_path:
        return {
            "available": False,
            "reason": "officecli binary not found",
            "hint": "npm install -g officecli  # or ./scripts/aida_setup_officecli.sh",
            "policy": _policy_note(),
        }
    version = None
    try:
        r = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        version = (r.stdout or r.stderr or "").strip().splitlines()[:1]
        version = version[0] if version else None
    except Exception as exc:  # noqa: BLE001
        version = f"probe_error:{exc}"[:80]

    cfg_path = _config_path()
    runtime_mode = None
    gen_configured = False
    publish_on = None
    llm_base = None
    llm_model = None
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            runtime_mode = (raw.get("runtime") or {}).get("mode")
            llm = raw.get("llm") or {}
            llm_base = llm.get("base_url")
            llm_model = llm.get("model")
            gen_configured = bool(llm.get("base_url") and llm.get("api_key"))
            publish_on = (raw.get("publish") or {}).get("enabled") or (
                raw.get("defaults") or {}
            ).get("publish")
        except Exception:  # noqa: BLE001
            pass

    litellm_ok = False
    try:
        import httpx

        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{LITELLM_BASE}/health/liveliness")
            litellm_ok = r.status_code == 200
    except Exception:  # noqa: BLE001
        litellm_ok = False

    return {
        "available": True,
        "bin": bin_path,
        "version": version,
        "runtime_mode": runtime_mode,
        "generation_configured": gen_configured,
        "publish_default": publish_on,
        "llm_base_url": llm_base,
        "llm_model": llm_model,
        "litellm_base": LITELLM_BASE,
        "litellm_reachable": litellm_ok,
        "allow_hosted": ALLOW_HOSTED,
        "allow_remote": ALLOW_REMOTE,
        "kinds": list(KIND_EXTS.keys()),
        "config_path": str(cfg_path),
        "policy": _policy_note(),
        "manager_role": (
            "Document output orchestrator candidate: generate PPTX/DOCX/XLSX "
            "from style packs + briefs; hand off DOCX to adeu for redline; "
            "A.I.D.A. for a11y export of any PDF artifact."
        ),
    }


def _policy_note() -> dict[str, Any]:
    return {
        "default_runtime": "external",
        "default_publish": False,
        "hosted_default": False,
        "phi": "Use local LiteLLM only; medical categories refuse hosted",
        "prepare_only": True,
        "submit_ready_default": False,
    }


def _slug(topic: str, limit: int = 48) -> str:
    s = re.sub(r"[^\w\s-]", "", topic, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "_", s).strip("_").lower()
    return (s or "document")[:limit]


def generate(
    kind: str,
    topic: str,
    *,
    prompt: str | None = None,
    prompt_file: str | Path | None = None,
    out_dir: str | Path | None = None,
    category: str | None = None,
    mode: str = "fast",
    style: str | None = None,
    audience: str | None = None,
    lang: str | None = None,
    no_images: bool = True,
    file: str | Path | None = None,
    force_external: bool = True,
    allow_publish: bool = False,
) -> dict[str, Any]:
    """Run officecli new <kind> with local-first policy."""
    t0 = time.perf_counter()
    kind = (kind or "").strip().lower()
    if kind not in KIND_EXTS:
        return {
            "status": "error",
            "error": f"unsupported kind {kind!r}; use one of {list(KIND_EXTS)}",
        }
    if not (topic or "").strip():
        return {"status": "error", "error": "topic is required"}

    avail = officecli_available()
    if not avail.get("available"):
        return {
            "status": "unavailable",
            "error": avail.get("reason"),
            "hint": avail.get("hint"),
        }

    cat = (category or "").strip().lower()
    phi_sensitive = cat in PHI_CATEGORIES or cat.startswith("medical")
    if phi_sensitive and ALLOW_HOSTED is False:
        # already policy; ensure external
        force_external = True
    if phi_sensitive and ALLOW_REMOTE:
        # still force external local path for PHI even if remote otherwise allowed
        pass
    if phi_sensitive and not ALLOW_REMOTE:
        # verify we are not accidentally hosted
        if (avail.get("runtime_mode") or "") == "hosted" and not force_external:
            return {
                "status": "error",
                "error": "PHI category refuses hosted officecli; configure external LiteLLM",
                "category": cat,
            }

    if force_external:
        ensure_external_config(publish=False)

    if not prompt and not prompt_file:
        prompt = (
            f"Create a clear, professional {kind.upper()} about: {topic}. "
            "Use hierarchical headings, short paragraphs, and actionable next steps. "
            "Do not invent medical diagnoses, legal conclusions, or private patient data."
        )

    # Output under ingest prep for MANAGER orchestration
    if out_dir:
        dest_dir = Path(out_dir).expanduser().resolve()
    else:
        from pipeline import ingest_root, CATEGORIES

        c = category if category in CATEGORIES else "_unsorted"
        dest_dir = ingest_root() / c / "_prep" / "officecli"
    dest_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_bin()
    assert bin_path
    cmd = [
        bin_path,
        "new",
        kind,
        topic,
        "--mode",
        mode if mode in ("fast", "best") else "fast",
        "--out",
        str(dest_dir),
        "--json",
        "--no-publish",
    ]
    if not allow_publish:
        # already --no-publish
        pass
    if prompt_file:
        pf = Path(prompt_file).expanduser().resolve()
        if not pf.is_file():
            return {"status": "error", "error": f"prompt_file not found: {pf}"}
        cmd.extend(["--prompt-file", str(pf)])
    elif prompt:
        cmd.extend(["--prompt", prompt])
    if style:
        cmd.extend(["--style", style])
    if audience:
        cmd.extend(["--audience", audience])
    if lang:
        cmd.extend(["--lang", lang])
    if kind == "pptx" and no_images:
        cmd.append("--no-images")
    if kind == "report":
        if not file:
            return {"status": "error", "error": "report requires file= path to source xlsx"}
        fp = Path(file).expanduser().resolve()
        if not fp.is_file():
            return {"status": "error", "error": f"workbook not found: {fp}"}
        cmd.extend(["--file", str(fp)])

    # Persist prompt for MANAGER reproducibility
    stem = _slug(topic)
    prompt_path = dest_dir / f"{stem}.prompt.md"
    try:
        prompt_path.write_text(
            prompt
            or (
                Path(prompt_file).read_text(encoding="utf-8")
                if prompt_file
                else ""
            ),
            encoding="utf-8",
        )
    except OSError:
        prompt_path = None

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=OFFICECLI_TIMEOUT,
            cwd=str(dest_dir),
            env={**os.environ, "PATH": f"{Path(bin_path).parent}:{os.environ.get('PATH','')}"},
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": f"officecli timed out after {OFFICECLI_TIMEOUT}s",
            "kind": kind,
            "topic": topic,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:400], "kind": kind}

    parsed: dict[str, Any] | None = None
    stdout = r.stdout or ""
    stderr = r.stderr or ""
    # Try parse JSON from stdout
    for blob in (stdout, stderr):
        blob = blob.strip()
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
            break
        except json.JSONDecodeError:
            # find last {...}
            m = re.search(r"\{[\s\S]*\}\s*$", blob)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    break
                except json.JSONDecodeError:
                    pass

    # Discover newest artifact of expected type
    ext = KIND_EXTS[kind]
    artifacts = sorted(
        dest_dir.glob(f"*{ext}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    output_path = None
    if parsed:
        for key in (
            "file_path",
            "path",
            "output",
            "file",
            "filepath",
            "out",
            "document_path",
        ):
            if parsed.get(key) and Path(str(parsed[key])).is_file():
                output_path = str(Path(parsed[key]).resolve())
                break
        if not output_path and isinstance(parsed.get("files"), list) and parsed["files"]:
            f0 = parsed["files"][0]
            if isinstance(f0, str) and Path(f0).is_file():
                output_path = str(Path(f0).resolve())
            elif isinstance(f0, dict):
                for key in ("path", "file", "output"):
                    if f0.get(key) and Path(str(f0[key])).is_file():
                        output_path = str(Path(f0[key]).resolve())
                        break
    if not output_path and artifacts:
        output_path = str(artifacts[0])

    ok = r.returncode == 0 and output_path is not None
    meta = {
        "status": "ok" if ok else "error",
        "engine": "officecli",
        "kind": kind,
        "topic": topic,
        "category": category,
        "mode": mode,
        "output": output_path,
        "out_dir": str(dest_dir),
        "prompt_path": str(prompt_path) if prompt_path else None,
        "returncode": r.returncode,
        "stdout_tail": stdout[-1500:],
        "stderr_tail": stderr[-800:],
        "cli_json": parsed,
        "runtime": "external",
        "publish": False,
        "no_images": no_images if kind == "pptx" else None,
        "hitl_required": True,
        "submit_ready": False,
        "decision_authority": "prepare_only",
        "phi_category": phi_sensitive,
        "manager_orchestration": {
            "next_adeu_redline": kind == "docx" and bool(output_path),
            "next_aida_a11y": kind in ("docx", "pptx") and bool(output_path),
            "style_pack_optional": True,
            "note": (
                "MANAGER can chain: officecli generate → adeu redline (docx) → "
                "A.I.D.A. linear HTML / veraPDF on export PDF"
            ),
        },
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "error": None
        if ok
        else (stderr[:400] or stdout[:400] or f"returncode={r.returncode}"),
    }
    # Write receipt next to artifact
    try:
        receipt = dest_dir / f"{stem}.{kind}.officecli_receipt.json"
        safe_meta = {**meta, "cli_json": parsed}
        receipt.write_text(json.dumps(safe_meta, indent=2, default=str), encoding="utf-8")
        meta["receipt_path"] = str(receipt)
    except OSError:
        pass
    return meta


def list_outputs(category: str | None = None, limit: int = 50) -> dict[str, Any]:
    from pipeline import ingest_root, CATEGORIES

    root = ingest_root()
    cats = [category] if category and category in CATEGORIES else list(CATEGORIES.keys())
    items: list[dict[str, Any]] = []
    for c in cats:
        d = root / c / "_prep" / "officecli"
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() in {
                ".pptx",
                ".docx",
                ".xlsx",
                ".html",
                ".png",
                ".gif",
                ".json",
                ".md",
            }:
                items.append(
                    {
                        "path": str(p),
                        "category": c,
                        "name": p.name,
                        "bytes": p.stat().st_size,
                        "mtime": p.stat().st_mtime,
                    }
                )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return {"count": len(items), "items": items[:limit]}
