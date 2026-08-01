#!/usr/bin/env python3
"""OpenDataLoader PDF — optional Adobe-free auto-tag → Tagged PDF.

Apache-2.0 core. Claims free Tagged PDF (Well-Tagged PDF direction);
full PDF/UA-1/2 export is enterprise — we never claim PDF/UA without
our own veraPDF pass.

Requires Java 11+ and: pip install opendataloader-pdf

Doctrine (ChatGPT / OSS research): no mature Acrobat Auto-Tag equivalent.
This is a candidate smoke path only — measure with veraPDF on your corpus.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

ODL_DISABLE = os.environ.get("AIDA_OPENDATALOADER_DISABLE", "0") == "1"
# When "auto", use if package+java present; "1" force try; "0" same as disable
ODL_ENABLE = os.environ.get("AIDA_OPENDATALOADER", "auto").strip().lower()


def _candidate_java_bins() -> list[str]:
    """Prefer AIDA_JAVA_HOME / brew openjdk@17 over stale system Java 8."""
    cands: list[str] = []
    env_java = os.environ.get("AIDA_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if env_java:
        p = Path(env_java) / "bin" / "java"
        if p.is_file():
            cands.append(str(p))
    # Homebrew openjdk@17 (Apple Silicon + Intel)
    for prefix in (
        "/opt/homebrew/opt/openjdk@17",
        "/usr/local/opt/openjdk@17",
        "/opt/homebrew/opt/openjdk",
        "/usr/local/opt/openjdk",
    ):
        for rel in (
            "bin/java",
            "libexec/openjdk.jdk/Contents/Home/bin/java",
        ):
            p = Path(prefix) / rel
            if p.is_file():
                cands.append(str(p.resolve()))
    which = shutil.which("java")
    if which:
        cands.append(which)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _java_version(java: str) -> tuple[int, list[str], str]:
    r = subprocess.run(
        [java, "-version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    raw = r.stderr or r.stdout or ""
    ver = raw.splitlines()[:3]
    major = 0
    import re

    m = re.search(r'version "(\d+)(?:\.(\d+))?', raw)
    if m:
        major = int(m.group(1))
        if major == 1 and m.group(2):
            major = int(m.group(2))
    return major, ver, raw


def _java_ok() -> dict[str, Any]:
    cands = _candidate_java_bins()
    if not cands:
        return {
            "available": False,
            "reason": "java not found (need JDK 11+)",
            "hint": "brew install openjdk@17 && export PATH=\"$(brew --prefix openjdk@17)/bin:$PATH\"",
        }
    tried: list[dict[str, Any]] = []
    for java in cands:
        try:
            major, ver, _raw = _java_version(java)
            tried.append({"java": java, "major": major, "version": ver[0] if ver else None})
            if major >= 11:
                # Ensure child processes (opendataloader JVM) prefer this java
                home = str(Path(java).resolve().parent.parent)
                os.environ.setdefault("JAVA_HOME", home)
                # Prepend to PATH for subprocesses
                jbin = str(Path(java).resolve().parent)
                path = os.environ.get("PATH", "")
                if jbin not in path.split(":"):
                    os.environ["PATH"] = f"{jbin}:{path}"
                return {
                    "available": True,
                    "java": java,
                    "major": major,
                    "version_lines": ver,
                    "JAVA_HOME": home,
                }
        except Exception as exc:  # noqa: BLE001
            tried.append({"java": java, "error": str(exc)[:120]})
    best = tried[0] if tried else {}
    return {
        "available": False,
        "reason": (
            f"Java {best.get('major') or '?'} found; OpenDataLoader needs JDK 11+ "
            f"(tried: {best.get('java')})"
        ),
        "hint": "brew install openjdk@17 && export PATH=\"$(brew --prefix openjdk@17)/bin:$PATH\"",
        "tried": tried[:6],
    }


def opendataloader_available() -> dict[str, Any]:
    if ODL_DISABLE or ODL_ENABLE in ("0", "false", "no", "off"):
        return {
            "available": False,
            "reason": "disabled via AIDA_OPENDATALOADER_DISABLE or AIDA_OPENDATALOADER=0",
            "license": "Apache-2.0 (core + free tagged-pdf)",
            "pdf_ua_export": "enterprise_not_used",
            "adobe": "not used",
        }
    java = _java_ok()
    if not java.get("available"):
        return {
            "available": False,
            "reason": java.get("reason"),
            "hint": java.get("hint")
            or "Install JDK 11+ (e.g. brew install openjdk@17) then pip install opendataloader-pdf",
            "java": java,
            "license": "Apache-2.0",
            "pdf_ua_export": "enterprise_not_used",
        }
    try:
        import opendataloader_pdf  # noqa: F401

        return {
            "available": True,
            "package": "opendataloader-pdf",
            "java": java,
            "license": "Apache-2.0 (core + free auto-tag → Tagged PDF)",
            "pdf_ua_export": "enterprise_not_used",
            "adobe": "not used",
            "note": (
                "Candidate auto-tag only. Always re-run veraPDF. "
                "Not claimed as Acrobat Auto-Tag equivalent or certified PDF/UA."
            ),
        }
    except ImportError as exc:
        return {
            "available": False,
            "reason": f"opendataloader-pdf not installed: {exc}",
            "hint": "pip install opendataloader-pdf  # needs Java 11+",
            "java": java,
            "license": "Apache-2.0",
            "pdf_ua_export": "enterprise_not_used",
        }


def convert_to_tagged_pdf(
    pdf_path: str | Path,
    *,
    out_dir: Path,
    stem: str | None = None,
) -> dict[str, Any]:
    """Untagged PDF in → Tagged PDF out (best effort)."""
    t0 = time.perf_counter()
    src = Path(pdf_path).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"not found: {src}", "engine": "opendataloader"}
    if src.suffix.lower() != ".pdf":
        return {"status": "skipped", "reason": "not a pdf", "engine": "opendataloader"}

    avail = opendataloader_available()
    if not avail.get("available"):
        return {
            "status": "unavailable",
            "engine": "opendataloader",
            "reason": avail.get("reason"),
            "hint": avail.get("hint"),
            "license": avail.get("license"),
        }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = stem or src.stem
    # OpenDataLoader writes into output_dir; we normalize to our name after
    try:
        import opendataloader_pdf

        opendataloader_pdf.convert(
            input_path=[str(src)],
            output_dir=str(out_dir),
            format="tagged-pdf",
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "engine": "opendataloader",
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    # Find produced PDF (name may match source stem)
    candidates = sorted(
        out_dir.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    produced: Path | None = None
    for c in candidates:
        # Prefer newly written, not our final name if already exists from prior run
        if c.name.endswith(".tagged.pdf"):
            produced = c
            break
        if c.stem == src.stem or c.stem.startswith(src.stem):
            produced = c
            break
    if produced is None and candidates:
        produced = candidates[0]

    if produced is None or not produced.is_file():
        return {
            "status": "error",
            "engine": "opendataloader",
            "error": "convert returned but no PDF found in output_dir",
            "output_dir": str(out_dir),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    dest = out_dir / f"{s}.tagged.pdf"
    if produced.resolve() != dest.resolve():
        try:
            shutil.copy2(produced, dest)
        except OSError:
            dest = produced

    return {
        "status": "ok",
        "engine": "opendataloader",
        "tag_engine": "opendataloader",
        "source": str(src),
        "output": str(dest),
        "bytes": dest.stat().st_size,
        "license": avail.get("license"),
        "pdf_ua_certified": False,
        "pdf_ua_export": "enterprise_not_used",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "note": (
            "Tagged PDF candidate (Apache-2.0 free path). "
            "Not certified PDF/UA until veraPDF pdf_ua_pass is true. "
            "Not an Acrobat Auto-Tag equivalent."
        ),
    }
