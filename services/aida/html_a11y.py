#!/usr/bin/env python3
"""Linear HTML export + optional axe-core (npx) for hybrid a11y signals.

WAVE is proprietary SaaS — not automated here. axe-core via npx is the
open-source multi-method stand-in for web-layer checks on exported HTML.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

AXE_TIMEOUT = int(os.environ.get("AIDA_AXE_TIMEOUT", "120"))
AXE_DISABLE = os.environ.get("AIDA_AXE_DISABLE", "0") == "1"

# browser-driver-manager default layout (mac_arm)
_BDM_ROOT = Path.home() / ".browser-driver-manager"


def _esc(s: Any) -> str:
    t = str(s or "")
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def text_to_linear_html(
    text: str,
    *,
    title: str,
    stem: str,
    caregiver_summary: str = "",
    plain_summary: str = "",
) -> str:
    """Build high-contrast linear HTML suitable for VoiceOver / axe."""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", (text or "")[:20000]):
        block = block.strip()
        if not block:
            continue
        # heading-like
        if re.match(r"^[A-Z][A-Za-z0-9 /&:-]{2,70}$", block) and len(block) < 80:
            paragraphs.append(f"<h2>{_esc(block)}</h2>")
        else:
            lines = block.splitlines()
            if len(lines) > 1 and all(len(ln) < 100 for ln in lines[:8]):
                items = "".join(f"<li>{_esc(ln.strip())}</li>" for ln in lines if ln.strip())
                paragraphs.append(f"<ul>{items}</ul>")
            else:
                paragraphs.append(f"<p>{_esc(block)}</p>")

    main_body = "\n".join(paragraphs) or "<p>(No extractable text)</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 18px;
      line-height: 1.55;
      max-width: 42rem;
      margin: 1.5rem auto;
      padding: 0 1rem;
      color: #111;
      background: #fff;
    }}
    h1, h2 {{ font-weight: 700; color: #000; }}
    a {{ color: #003f8c; }}
    .meta {{ color: #222; font-size: 0.95rem; }}
    /* WCAG-oriented high contrast */
  </style>
</head>
<body>
  <header>
    <h1>Accessible document export — {_esc(stem)}</h1>
    <p class="meta">A.I.D.A. prepare-only linear HTML. HITL screen-reader check pending.</p>
  </header>
  <main>
    <section aria-labelledby="plain">
      <h2 id="plain">Plain language</h2>
      <p>{_esc(plain_summary or "See document text below.")}</p>
    </section>
    <section aria-labelledby="care">
      <h2 id="care">Caregiver notes</h2>
      <p>{_esc(caregiver_summary or "")}</p>
    </section>
    <section aria-labelledby="doc">
      <h2 id="doc">Document text (linear)</h2>
      {main_body}
    </section>
  </main>
</body>
</html>
"""


def write_document_html(
    path: Path,
    text: str,
    *,
    stem: str,
    caregiver_summary: str = "",
    plain_summary: str = "",
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = text_to_linear_html(
        text,
        title=f"A.I.D.A. export — {stem}",
        stem=stem,
        caregiver_summary=caregiver_summary,
        plain_summary=plain_summary,
    )
    path.write_text(html, encoding="utf-8")
    return str(path)


def _newest_match(root: Path, pattern: str) -> Path | None:
    if not root.is_dir():
        return None
    matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for m in matches:
        if m.is_file() and os.access(m, os.X_OK):
            return m
    return None


def resolve_chromedriver() -> str | None:
    """Prefer env, then browser-driver-manager install, then PATH."""
    for key in ("AIDA_CHROMEDRIVER_PATH", "CHROMEDRIVER_TEST_PATH", "CHROMEDRIVER_PATH"):
        v = os.environ.get(key, "").strip()
        if v and Path(v).is_file():
            return v
    # browser-driver-manager layout
    found = _newest_match(
        _BDM_ROOT / "chromedriver",
        "**/chromedriver-mac-arm64/chromedriver",
    ) or _newest_match(_BDM_ROOT / "chromedriver", "**/chromedriver")
    if found:
        return str(found)
    which = shutil.which("chromedriver")
    return which


def resolve_chrome_binary() -> str | None:
    for key in ("AIDA_CHROME_PATH", "CHROME_TEST_PATH", "CHROME_BIN", "CHROME_PATH"):
        v = os.environ.get(key, "").strip()
        if v and Path(v).exists():
            return v
    found = _newest_match(
        _BDM_ROOT / "chrome",
        "**/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    )
    if found:
        return str(found)
    # system Chrome
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return str(mac)
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")


def axe_available() -> dict[str, Any]:
    if AXE_DISABLE:
        return {"available": False, "reason": "AIDA_AXE_DISABLE=1"}
    npx = shutil.which("npx")
    if not npx:
        return {"available": False, "reason": "npx not on PATH"}
    driver = resolve_chromedriver()
    chrome = resolve_chrome_binary()
    return {
        "available": True,
        "npx": npx,
        "package": "@axe-core/cli",
        "chromedriver": driver,
        "chrome": chrome,
        "ready": bool(driver and chrome),
        "setup_hint": None
        if (driver and chrome)
        else "Run: npx browser-driver-manager install chrome  (or ./scripts/aida_setup_axe.sh)",
    }


def run_axe_on_html(html_path: str | Path) -> dict[str, Any]:
    """Run axe-core CLI against a local HTML file (WAVE substitute)."""
    path = Path(html_path).expanduser().resolve()
    if not path.is_file():
        return {"status": "error", "error": f"not found: {path}", "violations_count": 0}
    avail = axe_available()
    if not avail.get("available"):
        return {
            "status": "unavailable",
            "engine": "axe-core",
            "note": avail.get("reason"),
            "violations_count": 0,
            "violations": [],
        }

    npx = avail["npx"]
    driver = resolve_chromedriver()
    chrome = resolve_chrome_binary()
    url = path.as_uri()
    cmd = [
        npx,
        "--yes",
        "@axe-core/cli",
        url,
        "--stdout",
        "--exit",
    ]
    if driver:
        cmd.extend(["--chromedriver-path", driver])
    if chrome:
        cmd.extend(["--chrome-path", chrome])

    env = os.environ.copy()
    if driver:
        env["CHROMEDRIVER_PATH"] = driver
        env["CHROMEDRIVER_TEST_PATH"] = driver
    if chrome:
        env["CHROME_BIN"] = chrome
        env["CHROME_TEST_PATH"] = chrome

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=AXE_TIMEOUT,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "engine": "axe-core", "violations_count": 0}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "engine": "axe-core", "error": str(exc)[:300], "violations_count": 0}

    raw = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = f"{raw}\n{err}"
    # Chrome/driver mismatch or missing browser → not a clean a11y result
    if re.search(
        r"session not created|ChromeDriver only supports|browser-driver-manager|ECONNREFUSED",
        combined,
        re.I,
    ):
        return {
            "status": "unavailable",
            "engine": "axe-core",
            "mode": "cli_browser_missing",
            "returncode": proc.returncode,
            "violations_count": 0,
            "violations": [],
            "chromedriver": driver,
            "chrome": chrome,
            "stderr_tail": err[-500:],
            "note": (
                "axe-core needs a matching Chrome + ChromeDriver. "
                "Run: ./scripts/aida_setup_axe.sh "
                "— or set AIDA_AXE_DISABLE=1 and rely on veraPDF + HITL VoiceOver."
            ),
            "fallback": "contrast_self_check + linear HTML HITL",
        }

    # Prefer JSON (axe --stdout emits array or object)
    report = None
    if raw.startswith("{") or raw.startswith("["):
        try:
            report = json.loads(raw)
        except json.JSONDecodeError:
            # sometimes trailing noise
            start = raw.find("[")
            if start < 0:
                start = raw.find("{")
            end = raw.rfind("]")
            if end < 0:
                end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    report = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    report = None

    if report is None:
        m = re.search(r"(\d+)\s+violations?", raw, re.I)
        count = int(m.group(1)) if m else (0 if proc.returncode == 0 else -1)
        okish = proc.returncode in (0, 1) and "Error:" not in combined[:500]
        return {
            "status": "ok" if okish else "error",
            "engine": "axe-core",
            "mode": "cli_text",
            "returncode": proc.returncode,
            "violations_count": max(0, count) if count >= 0 else 0,
            "chromedriver": driver,
            "chrome": chrome,
            "stdout_tail": raw[-1500:],
            "stderr_tail": err[-400:],
            "note": "Parsed text summary; install axe JSON output if needed",
        }

    # axe --stdout often returns a list of result objects
    results = report if isinstance(report, list) else [report]
    violations: list[Any] = []
    for res in results:
        if not isinstance(res, dict):
            continue
        violations.extend(res.get("violations") or [])
        if not violations and "results" in res:
            r0 = (res.get("results") or [{}])[0]
            if isinstance(r0, dict):
                violations.extend(r0.get("violations") or [])

    simplified = []
    for v in violations[:30]:
        if not isinstance(v, dict):
            continue
        simplified.append(
            {
                "id": v.get("id"),
                "impact": v.get("impact"),
                "description": str(v.get("description") or "")[:200],
                "help": str(v.get("help") or "")[:200],
                "nodes": len(v.get("nodes") or []),
            }
        )

    return {
        "status": "ok",
        "engine": "axe-core",
        "mode": "cli_json",
        "returncode": proc.returncode,
        "violations_count": len(simplified) if simplified else len(violations),
        "violations": simplified,
        "chromedriver": driver,
        "chrome": chrome,
        "passes_note": "axe on linear HTML export — not full WAVE website audit",
    }


def contrast_self_check_html(html_path: str | Path) -> dict[str, Any]:
    """Static contrast check for our generated CSS (black on white)."""
    path = Path(html_path)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"status": "error", "error": str(exc)}
    # Our template uses #111 on #fff ≈ 17:1 — AA/AAA
    ok = "color: #111" in raw and "background: #fff" in raw
    return {
        "status": "ok",
        "engine": "contrast_self_check",
        "ratio_estimate": 17.0 if ok else None,
        "wcag_aa": ok,
        "wcag_aaa": ok,
        "note": "Applies to A.I.D.A.-generated HTML only; embedded PDF images not measured",
    }
