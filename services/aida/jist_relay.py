#!/usr/bin/env python3
"""JIST — Just In Simple Terms + emotional risk gate (local LLM only)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

LITELLM_BASE = os.environ.get("AIDA_LITELLM_BASE", "http://localhost:4000").rstrip("/")
LITELLM_KEY = os.environ.get("AIDA_LITELLM_KEY") or os.environ.get("LITELLM_MASTER_KEY", "")
AIDA_MODEL = os.environ.get("AIDA_MODEL", "role-phi-local")
AIDA_ALLOW_REMOTE = os.environ.get("AIDA_ALLOW_REMOTE", "0") == "1"

_REMOTE_MARKERS = (
    "openrouter",
    "gemini",
    "gpt-",
    "claude",
    "xai",
    "grok-",
    "anthropic",
    "openai/",
)

_EMOTIONAL_TERMS = re.compile(
    r"(?i)\b("
    r"cancer|malignant|terminal|hospice|palliative|died|death|deceased|"
    r"denial|denied|evict|foreclos|bankrupt|suicide|overdose|abuse|"
    r"stage\s*[ivx0-9]+|poor\s*prognosis|not\s*compatible\s*with\s*life"
    r")\b"
)


def _assert_local(model: str) -> None:
    if AIDA_ALLOW_REMOTE:
        return
    m = (model or "").lower()
    if any(x in m for x in _REMOTE_MARKERS):
        raise ValueError(f"JIST model {model!r} looks remote; PHI path requires local tier")


def emotional_risk_heuristic(text: str) -> dict[str, Any]:
    hits = sorted(set(_EMOTIONAL_TERMS.findall(text or "")))
    level = "low"
    if len(hits) >= 3:
        level = "high"
    elif hits:
        level = "medium"
    return {
        "emotional_risk_level": level,
        "trigger_terms": hits[:20],
        "engine": "heuristic",
        "note": "Heuristic only — K.A.R.E.N.-style soft gate, not clinical judgment",
    }


def build_jist(
    text: str,
    *,
    doc_kind: str,
    dual: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    preview = (text or "")[:6000]
    emo = emotional_risk_heuristic(preview)
    dual = dual or {}
    ce = dual.get("caregivee") or {}
    summary = str(ce.get("summary") or "This is a short plain-language summary of the document.")
    bullets = list(ce.get("gentle_bullets") or [
        "This is simplified language, not medical advice.",
        "Ask your care partner about any date or amount you do not understand.",
        "Keep the original document in a safe place.",
    ])

    llm_meta: dict[str, Any] = {"used": False}
    if use_llm and preview.strip():
        try:
            _assert_local(AIDA_MODEL)
            import httpx

            prompt = (
                "You are A.I.D.A. JIST (Just In Simple Terms). prepare_only.\n"
                "Write a calm 6th-grade summary for a care recipient.\n"
                "Return STRICT JSON: summary (string), bullets (3 short strings), "
                "tts_script (one soft paragraph for speech), emotional_risk_level "
                "(low|medium|high), accuracy_notes (string — what you are unsure about).\n"
                "Do not invent clinical facts. Soften scary wording without hiding real risks.\n\n"
                f"doc_kind={doc_kind}\nemotional_heuristic={emo['emotional_risk_level']}\n\n"
                f"DOCUMENT:\n{preview[:5000]}"
            )
            headers = {"Content-Type": "application/json"}
            if LITELLM_KEY:
                headers["Authorization"] = f"Bearer {LITELLM_KEY}"
            with httpx.Client(timeout=90.0) as client:
                r = client.post(
                    f"{LITELLM_BASE}/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": AIDA_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Return only valid JSON. prepare_only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 700,
                    },
                )
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{[\s\S]*\}", content)
            data = json.loads(m.group(0) if m else content)
            if data.get("summary"):
                summary = str(data["summary"])[:2000]
            if isinstance(data.get("bullets"), list):
                bullets = [str(x)[:200] for x in data["bullets"][:5]]
            tts = str(data.get("tts_script") or "")[:2000]
            if data.get("emotional_risk_level") in ("low", "medium", "high"):
                # take max of heuristic vs llm
                order = {"low": 0, "medium": 1, "high": 2}
                if order[data["emotional_risk_level"]] > order[emo["emotional_risk_level"]]:
                    emo["emotional_risk_level"] = data["emotional_risk_level"]
                    emo["engine"] = "heuristic+llm"
            llm_meta = {
                "used": True,
                "model": AIDA_MODEL,
                "accuracy_notes": str(data.get("accuracy_notes") or "")[:500],
            }
        except Exception as exc:  # noqa: BLE001
            llm_meta = {"used": False, "error": str(exc)[:300]}
            tts = (
                f"{summary} "
                + " ".join(bullets)
            )
    else:
        tts = f"{summary} " + " ".join(bullets)

    # Soft gate: high emotional risk → require HITL before caregiver share
    hitl = "pending"
    share_gate = "allow_with_caregiver"
    if emo["emotional_risk_level"] == "high":
        share_gate = "hitl_required_before_caregivee_share"
    elif emo["emotional_risk_level"] == "medium":
        share_gate = "prefer_caregiver_present"

    return {
        "summary": summary,
        "bullets": bullets,
        "tts_script": tts,
        "emotional_risk_level": emo["emotional_risk_level"],
        "emotional": emo,
        "share_gate": share_gate,
        "hitl_status": hitl,
        "llm": llm_meta,
        "doc_kind": doc_kind,
        "decision_authority": "prepare_only",
        "karen_style_gate": "emotional_soft_gate",
    }
