#!/usr/bin/env python3
"""Prompt I/O scanner — Vigil-compatible REST + Prometheus metrics.

Lightweight default scanners (heuristics) for local-first stacks.
Optional upstream forward to a full deadbits/vigil-llm instance via
PROMPT_IO_VIGIL_UPSTREAM (e.g. http://vigil:5000).

LiteLLM hybrid guardrail posts here with call_id for joinable metrics.
"""

from __future__ import annotations

import math
import os
import re
import time
import uuid
from collections import Counter
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter as PromCounter,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, Field

APP_NAME = "prompt-io-scanner"
PORT = int(os.environ.get("PROMPT_IO_PORT", "5050"))
VIGIL_UPSTREAM = os.environ.get("PROMPT_IO_VIGIL_UPSTREAM", "").rstrip("/")
FORWARD_TIMEOUT = float(os.environ.get("PROMPT_IO_FORWARD_TIMEOUT", "2.0"))
# Never store full prompt bodies in metrics; optional short hash for debug logs.
LOG_PROMPT_PREVIEW = os.environ.get("PROMPT_IO_LOG_PREVIEW", "0") == "1"

# --- Prometheus (low cardinality — never label by call_id) ---
SCAN_TOTAL = PromCounter(
    "prompt_io_scan_total",
    "Prompt I/O scans",
    ["mode", "outcome"],
)
SCAN_HITS = PromCounter(
    "prompt_io_scanner_hits_total",
    "Scanner hit counts",
    ["scanner"],
)
SCAN_LATENCY = Histogram(
    "prompt_io_scan_latency_seconds",
    "Scan latency",
    ["mode"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
INJECTION_FLAGS = PromCounter(
    "prompt_io_injection_flag_total",
    "Scans that flagged potential injection/jailbreak",
    ["mode"],
)

app = FastAPI(
    title=APP_NAME,
    description=(
        "Vigil-compatible prompt/response scanner for ai-gateway. "
        "Join records on call_id from LiteLLM x-litellm-call-id."
    ),
    version="0.1.0",
)

# Heuristic injection / jailbreak patterns (YARA-lite; not a substitute for full Vigil).
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("InstructionBypass", re.compile(r"ignore\s+(all\s+)?(previous|prior|earlier|above)\s+instructions?", re.I)),
    ("InstructionBypass", re.compile(r"disregard\s+(your|the)\s+(system|prior|previous)", re.I)),
    ("Jailbreak", re.compile(r"\bDAN\b|do\s+anything\s+now|developer\s+mode\s+enabled", re.I)),
    ("Jailbreak", re.compile(r"jailbreak|bypass\s+(your\s+)?(filters|safety|guardrails)", re.I)),
    ("SystemPromptExtract", re.compile(r"(reveal|show|print|dump)\s+(your\s+)?(system\s+)?prompt", re.I)),
    ("RoleHijack", re.compile(r"you\s+are\s+now\s+(a|an|my)\s+", re.I)),
    ("EncodingEvasion", re.compile(r"(base64|rot13)\s*[:=]\s*[A-Za-z0-9+/=]{16,}", re.I)),
]

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("Phone", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
]


class AnalyzePromptBody(BaseModel):
    prompt: str = Field(..., description="User/system prompt text to scan")
    call_id: Optional[str] = Field(None, description="LiteLLM x-litellm-call-id join key")
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class AnalyzeResponseBody(BaseModel):
    prompt: str
    response: str = Field(..., description="LLM response text")
    call_id: Optional[str] = None
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str = APP_NAME
    vigil_upstream: bool


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _run_local_scanners(text: str, *, include_pii: bool = True) -> dict[str, Any]:
    results: dict[str, Any] = {}
    messages: list[str] = []
    flagged = False

    yara_matches: list[dict[str, Any]] = []
    for rule_name, pat in _INJECTION_PATTERNS:
        if pat.search(text):
            yara_matches.append(
                {"rule_name": rule_name, "category": rule_name, "tags": ["PromptInjection"]}
            )
            flagged = True
    if yara_matches:
        results["scanner:heuristic"] = {"matches": yara_matches}
        SCAN_HITS.labels(scanner="heuristic").inc(len(yara_matches))
        messages.append("Potential prompt injection detected: heuristic signature(s)")

    if include_pii:
        pii_matches: list[dict[str, Any]] = []
        for label, pat in _PII_PATTERNS:
            found = pat.findall(text)
            if found:
                pii_matches.append({"type": label, "count": len(found)})
                SCAN_HITS.labels(scanner="pii").inc()
        if pii_matches:
            results["scanner:pii"] = {"matches": pii_matches}
            messages.append("Potential PII patterns detected")

    ent = _entropy(text[:8000])
    results["scanner:entropy"] = {"prompt_entropy": round(ent, 6)}
    SCAN_HITS.labels(scanner="entropy").inc()

    return {
        "flagged": flagged,
        "messages": messages,
        "results": results,
        "prompt_entropy": round(ent, 6),
    }


async def _forward_vigil(path: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not VIGIL_UPSTREAM:
        return None
    url = f"{VIGIL_UPSTREAM}{path}"
    try:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001 — fail-open hybrid
        return None
    return None


def _minimal_record(
    *,
    mode: str,
    call_id: Optional[str],
    model: Optional[str],
    local: dict[str, Any],
    upstream: Optional[dict[str, Any]],
    elapsed_ms: float,
) -> dict[str, Any]:
    """Never embed raw headers or full request objects (secret-leak class)."""
    flagged = bool(local.get("flagged"))
    if upstream:
        # Treat upstream messages/matches as additional signal
        um = upstream.get("messages") or []
        if um:
            flagged = True
    outcome = "flagged" if flagged else "clean"
    SCAN_TOTAL.labels(mode=mode, outcome=outcome).inc()
    if flagged:
        INJECTION_FLAGS.labels(mode=mode).inc()

    return {
        "status": "success",
        "uuid": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "call_id": call_id,
        "model": model,
        "mode": mode,
        "flagged": flagged,
        "messages": list(local.get("messages") or [])
        + list((upstream or {}).get("messages") or []),
        "errors": [],
        "results": local.get("results") or {},
        "upstream_vigil": bool(upstream),
        "upstream_uuid": (upstream or {}).get("uuid"),
        "prompt_entropy": local.get("prompt_entropy"),
        "elapsed_ms": round(elapsed_ms, 3),
        "service": APP_NAME,
    }


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", vigil_upstream=bool(VIGIL_UPSTREAM))


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze/prompt")
@app.post("/analyze")
async def analyze_prompt(body: AnalyzePromptBody) -> dict[str, Any]:
    t0 = time.perf_counter()
    with SCAN_LATENCY.labels(mode="prompt").time():
        local = _run_local_scanners(body.prompt, include_pii=True)
        upstream = await _forward_vigil(
            "/analyze/prompt",
            {"prompt": body.prompt},
        )
        # Some Vigil builds use /analyze
        if upstream is None and VIGIL_UPSTREAM:
            upstream = await _forward_vigil("/analyze", {"prompt": body.prompt})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    rec = _minimal_record(
        mode="prompt",
        call_id=body.call_id,
        model=body.model,
        local=local,
        upstream=upstream,
        elapsed_ms=elapsed_ms,
    )
    if LOG_PROMPT_PREVIEW:
        rec["prompt_preview"] = body.prompt[:80]
    return rec


@app.post("/analyze/response")
async def analyze_response(body: AnalyzeResponseBody) -> dict[str, Any]:
    t0 = time.perf_counter()
    combined = f"{body.prompt}\n---\n{body.response}"
    with SCAN_LATENCY.labels(mode="response").time():
        local = _run_local_scanners(combined, include_pii=True)
        # Prompt-response similarity proxy: high token overlap can indicate echo/leak
        prompt_tokens = set(re.findall(r"\w+", body.prompt.lower()))
        resp_tokens = set(re.findall(r"\w+", body.response.lower()))
        if prompt_tokens and resp_tokens:
            jaccard = len(prompt_tokens & resp_tokens) / max(1, len(prompt_tokens | resp_tokens))
            local.setdefault("results", {})["scanner:similarity"] = {
                "jaccard": round(jaccard, 4)
            }
            SCAN_HITS.labels(scanner="similarity").inc()
        upstream = await _forward_vigil(
            "/analyze/response",
            {"prompt": body.prompt, "response": body.response},
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return _minimal_record(
        mode="response",
        call_id=body.call_id,
        model=body.model,
        local=local,
        upstream=upstream,
        elapsed_ms=elapsed_ms,
    )


@app.get("/settings")
async def settings() -> dict[str, Any]:
    return {
        "service": APP_NAME,
        "port": PORT,
        "vigil_upstream": VIGIL_UPSTREAM or None,
        "forward_timeout": FORWARD_TIMEOUT,
        "scanners": ["heuristic", "pii", "entropy", "similarity"],
    }
