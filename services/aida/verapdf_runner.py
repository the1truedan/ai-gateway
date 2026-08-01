#!/usr/bin/env python3
"""veraPDF runner — host binary, Docker (amd64), or unavailable.

Priority:
  1. VERAPDF_CMD (absolute path or name on PATH)
  2. `verapdf` on PATH
  3. Docker image (VERAPDF_DOCKER_IMAGE), platform linux/amd64 by default
  4. status unavailable — pipeline falls back to heuristics
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

VERAPDF_CMD = os.environ.get("VERAPDF_CMD", "").strip()
VERAPDF_DOCKER_IMAGE = os.environ.get(
    "VERAPDF_DOCKER_IMAGE", "verapdf/cli:latest"
).strip()
VERAPDF_DOCKER_PLATFORM = os.environ.get("VERAPDF_DOCKER_PLATFORM", "linux/amd64").strip()
VERAPDF_FLAVOUR = os.environ.get("VERAPDF_FLAVOUR", "ua1").strip()  # ua1 | ua2
VERAPDF_TIMEOUT = int(os.environ.get("VERAPDF_TIMEOUT", "180"))
VERAPDF_DISABLE_DOCKER = os.environ.get("VERAPDF_DISABLE_DOCKER", "0") == "1"


def _which_verapdf() -> str | None:
    if VERAPDF_CMD:
        p = Path(VERAPDF_CMD).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        found = shutil.which(VERAPDF_CMD)
        if found:
            return found
    return shutil.which("verapdf")


def docker_available() -> bool:
    return shutil.which("docker") is not None


def verapdf_status() -> dict[str, Any]:
    host = _which_verapdf()
    if host:
        return {"available": True, "mode": "host", "cmd": host}
    if not VERAPDF_DISABLE_DOCKER and docker_available():
        return {
            "available": True,
            "mode": "docker",
            "image": VERAPDF_DOCKER_IMAGE,
            "platform": VERAPDF_DOCKER_PLATFORM,
            "note": "arm64 hosts use linux/amd64 emulation when image is amd64-only",
        }
    return {
        "available": False,
        "mode": "none",
        "note": "Install veraPDF or pull Docker image; pipeline uses structure heuristics",
    }


def run_verapdf(pdf_path: str | Path) -> dict[str, Any]:
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        return {"status": "error", "error": f"not found: {path}", "issues": ["file_missing"]}
    if path.suffix.lower() != ".pdf":
        return {
            "status": "skipped",
            "note": "veraPDF only applies to PDF",
            "issues": [],
            "pdf_ua_pass": None,
        }

    host = _which_verapdf()
    if host:
        return _run_host(host, path)
    if not VERAPDF_DISABLE_DOCKER and docker_available():
        return _run_docker(path)
    return {
        "status": "unavailable",
        "engine": "verapdf",
        "issues": ["verapdf_not_installed"],
        "pdf_ua_pass": None,
        "wcag_score": None,
        "note": "Install veraPDF CLI or enable Docker image for PDF/UA validation",
    }


def _run_host(cmd: str, path: Path) -> dict[str, Any]:
    # Greenfield CLI: --format json --flavour ua1
    args = [cmd, "--format", "json", "--flavour", VERAPDF_FLAVOUR, str(path)]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=VERAPDF_TIMEOUT,
            check=False,
        )
        return _parse_output(proc.stdout, proc.stderr, proc.returncode, mode="host")
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "engine": "verapdf", "mode": "host", "issues": ["timeout"]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "engine": "verapdf", "mode": "host", "error": str(exc)[:300], "issues": []}


def _run_docker(path: Path) -> dict[str, Any]:
    """Run veraPDF via Docker.

    Copy the PDF into a local temp dir first. Docker Desktop often cannot
    bind-mount NFS paths under /Volumes/ai-data (mkdir /host_mnt/... errors).
    """
    import tempfile

    name = path.name
    tmp_dir_obj = tempfile.TemporaryDirectory(prefix="aida_verapdf_")
    tmp_dir = Path(tmp_dir_obj.name)
    local_pdf = tmp_dir / name
    try:
        shutil.copy2(path, local_pdf)
    except OSError as exc:
        tmp_dir_obj.cleanup()
        return {
            "status": "error",
            "engine": "verapdf",
            "mode": "docker",
            "error": f"copy_for_docker_failed: {exc}"[:300],
            "issues": ["docker_copy_failed"],
            "image": VERAPDF_DOCKER_IMAGE,
        }

    args = [
        "docker",
        "run",
        "--rm",
        "--platform",
        VERAPDF_DOCKER_PLATFORM,
        "-v",
        f"{tmp_dir}:/data:ro",
        VERAPDF_DOCKER_IMAGE,
        "--format",
        "json",
        "--flavour",
        VERAPDF_FLAVOUR,
        f"/data/{name}",
    ]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=VERAPDF_TIMEOUT + 60,
            check=False,
        )
        result = _parse_output(proc.stdout, proc.stderr, proc.returncode, mode="docker")
        result["image"] = VERAPDF_DOCKER_IMAGE
        result["docker_mount"] = "local_temp_copy"
        return result
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "engine": "verapdf",
            "mode": "docker",
            "issues": ["timeout"],
            "image": VERAPDF_DOCKER_IMAGE,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "engine": "verapdf",
            "mode": "docker",
            "error": str(exc)[:300],
            "issues": ["docker_failed"],
            "image": VERAPDF_DOCKER_IMAGE,
        }
    finally:
        try:
            tmp_dir_obj.cleanup()
        except Exception:  # noqa: BLE001
            pass


def _parse_output(stdout: str, stderr: str, returncode: int, *, mode: str) -> dict[str, Any]:
    raw = (stdout or "").strip()
    issues: list[str] = []
    report: Any = None

    if raw:
        try:
            report = json.loads(raw)
        except json.JSONDecodeError:
            # Some builds emit JSON after log lines
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    report = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    report = None

    pdf_ua_pass: bool | None = None
    failed_rules = 0
    passed_rules = 0

    if isinstance(report, dict):
        # veraPDF JSON structures vary slightly by version; handle common shapes
        root = report.get("report", report)
        jobs = root.get("jobs") if isinstance(root, dict) else None
        if jobs is None and "validationResult" in report:
            jobs = [report]
        if isinstance(jobs, list) and jobs:
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                texc = job.get("taskException")
                if isinstance(texc, dict) and not texc.get("success", True):
                    issues.append(f"parse_error:{texc.get('type') or 'TASK'}")
                    if texc.get("exceptionMessage"):
                        issues.append(str(texc["exceptionMessage"])[:120])
                    pdf_ua_pass = False
                vrs = job.get("validationResult") or job.get("validationResults") or []
                if isinstance(vrs, dict):
                    vrs = [vrs]
                for vr in vrs:
                    if not isinstance(vr, dict):
                        continue
                    if "compliant" in vr:
                        pdf_ua_pass = bool(vr["compliant"]) if pdf_ua_pass is None else (
                            pdf_ua_pass and bool(vr["compliant"])
                        )
                    details = vr.get("details") or {}
                    failed_rules += int(details.get("failedRules") or 0)
                    passed_rules += int(details.get("passedRules") or 0)
                    for rule in details.get("ruleSummaries") or []:
                        if rule.get("ruleStatus") == "FAILED" or rule.get("failedChecks"):
                            rid = rule.get("clause") or rule.get("specification") or rule.get("ruleId")
                            if rid:
                                issues.append(f"failed_rule:{rid}")
        # batch summary parse failures
        batch = root.get("batchSummary") if isinstance(root, dict) else None
        if isinstance(batch, dict) and int(batch.get("failedParsingJobs") or 0) > 0:
            issues.append("failed_parsing_jobs")
            if pdf_ua_pass is None:
                pdf_ua_pass = False
        # top-level compliant
        if pdf_ua_pass is None and "compliant" in report:
            pdf_ua_pass = bool(report["compliant"])


    # Exit code: 0 = compliant in many builds; 1 = not compliant; higher = error
    if pdf_ua_pass is None and returncode == 0 and report is not None:
        pdf_ua_pass = True
    elif pdf_ua_pass is None and returncode == 1 and report is not None:
        pdf_ua_pass = False

    if pdf_ua_pass is True:
        wcag_score = 95.0 if failed_rules == 0 else max(70.0, 95.0 - failed_rules * 2)
    elif pdf_ua_pass is False:
        wcag_score = max(20.0, 55.0 - min(failed_rules, 20) * 1.5)
    else:
        wcag_score = None

    status = "ok" if report is not None else ("error" if returncode not in (0, 1) else "ok")
    if report is None and returncode not in (0, 1):
        issues.append("parse_failed")
        if stderr:
            issues.append("stderr_present")

    out: dict[str, Any] = {
        "status": status if report is not None or returncode in (0, 1) else "error",
        "engine": "verapdf",
        "mode": mode,
        "flavour": VERAPDF_FLAVOUR,
        "returncode": returncode,
        "pdf_ua_pass": pdf_ua_pass,
        "failed_rules": failed_rules,
        "passed_rules": passed_rules,
        "wcag_score": wcag_score,
        "issues": issues[:50],
        "stderr_tail": (stderr or "")[-400:] if report is None else "",
    }
    if report is not None:
        out["report_summary"] = {
            "failed_rules": failed_rules,
            "passed_rules": passed_rules,
            "compliant": pdf_ua_pass,
        }
        # Keep a small raw slice for debugging (not full multi-MB reports)
        try:
            raw_compact = json.dumps(report)[:4000]
            out["report_json_head"] = raw_compact
        except (TypeError, ValueError):
            pass
    return out
