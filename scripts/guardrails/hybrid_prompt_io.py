"""Hybrid parallel prompt I/O guardrail for LiteLLM.

Runs Vigil-compatible scans (services/prompt_io) in parallel with the LLM
call (during_call) and audits responses (post_call). Always fail-open so
scanner downtime does not break the Headroom → LiteLLM path.

Join key: LiteLLM call_id (x-litellm-call-id / litellm_call_id).

Mount this file into the LiteLLM container as /app/hybrid_prompt_io.py and
reference hybrid_prompt_io.HybridPromptIOGuardrail in litellm_config.yaml.
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal, Optional, Union

from litellm._logging import verbose_proxy_logger
from litellm.caching.caching import DualCache
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.llms.custom_httpx.http_handler import (
    get_async_httpx_client,
    httpxSpecialProvider,
)
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.utils import CallTypes

PROMPT_IO_BASE = os.environ.get("PROMPT_IO_BASE", "http://prompt-io:5050").rstrip("/")
PROMPT_IO_TIMEOUT = float(os.environ.get("PROMPT_IO_TIMEOUT", "0.5"))
PROMPT_IO_ENABLED = os.environ.get("PROMPT_IO_ENABLED", "1") not in ("0", "false", "False")
# When 1, flagged prompts raise (fail-closed). Default 0 = metrics-only fail-open.
PROMPT_IO_BLOCK = os.environ.get("PROMPT_IO_BLOCK", "0") in ("1", "true", "True")


def _extract_text_from_messages(messages: Any) -> str:
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, str):
                    parts.append(block)
    return "\n".join(parts)


def _call_id_from_data(data: dict) -> Optional[str]:
    # Prefer explicit ids LiteLLM already assigned; never invent from headers dump.
    for key in ("litellm_call_id", "call_id", "id"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict):
        for key in ("litellm_call_id", "call_id"):
            val = metadata.get(key)
            if isinstance(val, str) and val:
                return val
    litellm_params = data.get("litellm_params") or {}
    if isinstance(litellm_params, dict):
        meta = litellm_params.get("metadata") or {}
        if isinstance(meta, dict):
            for key in ("litellm_call_id", "call_id"):
                val = meta.get(key)
                if isinstance(val, str) and val:
                    return val
    return None


def _model_from_data(data: dict) -> Optional[str]:
    m = data.get("model")
    return m if isinstance(m, str) else None


def _response_text(response: Any) -> str:
    try:
        choices = getattr(response, "choices", None) or []
        parts: list[str] = []
        for ch in choices:
            msg = getattr(ch, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content:
                    parts.append(content)
                # Some local models put draft text in reasoning_content with empty content
                reasoning = getattr(msg, "reasoning_content", None)
                if isinstance(reasoning, str) and reasoning:
                    parts.append(reasoning)
            text = getattr(ch, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
        return "\n".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def _stamp_metadata(data: dict, scan: dict[str, Any], *, phase: str) -> None:
    """Attach minimal scan summary for spend logs / standard logging — no secrets."""
    summary = {
        "phase": phase,
        "uuid": scan.get("uuid"),
        "call_id": scan.get("call_id"),
        "flagged": bool(scan.get("flagged")),
        "elapsed_ms": scan.get("elapsed_ms"),
        "messages": (scan.get("messages") or [])[:5],
        "scanner_keys": list((scan.get("results") or {}).keys())[:12],
        "service": scan.get("service"),
    }
    meta = data.setdefault("metadata", {})
    if not isinstance(meta, dict):
        return
    hybrid = meta.setdefault("hybrid_prompt_io", {})
    if not isinstance(hybrid, dict):
        hybrid = {}
        meta["hybrid_prompt_io"] = hybrid
    hybrid[phase] = summary


class HybridPromptIOGuardrail(CustomGuardrail):
    """Fail-open hybrid scanner bridge (Vigil-compatible prompt-io service)."""

    def __init__(self, **kwargs: Any) -> None:
        self.optional_params = kwargs
        self.api_base = (
            kwargs.get("api_base")
            or kwargs.get("prompt_io_base")
            or PROMPT_IO_BASE
        ).rstrip("/")
        self.timeout = float(kwargs.get("timeout") or PROMPT_IO_TIMEOUT)
        self.block_on_flag = bool(kwargs.get("block_on_flag", PROMPT_IO_BLOCK))
        super().__init__(**kwargs)

    async def apply_guardrail(self, *args: Any, **kwargs: Any) -> Any:
        """LiteLLM during_call / unified guardrail path.

        LiteLLM 1.92+ passes GenericGuardrailAPIInputs:
          apply_guardrail(inputs={"texts": [...], ...}, request_data=data, input_type=...)
        and expects the same mapping returned (must support .get("texts")).

        Older docs used apply_guardrail(text=...). Fail-open unless PROMPT_IO_BLOCK=1.
        """
        inputs = kwargs.get("inputs")
        request_data = kwargs.get("request_data")
        text = kwargs.get("text")
        input_type = kwargs.get("input_type")  # "request" | "response" | None

        if text is None and args and isinstance(args[0], str):
            text = args[0]

        # 1.92 GenericGuardrailAPIInputs (TypedDict / dict with texts list)
        if text is None and isinstance(inputs, dict):
            texts = inputs.get("texts") or []
            if isinstance(texts, list) and texts:
                text = "\n".join(str(t) for t in texts if t)
            elif inputs.get("structured_messages"):
                text = _extract_text_from_messages(inputs.get("structured_messages"))
        elif text is None and isinstance(inputs, str):
            text = inputs
        elif text is None and isinstance(inputs, list):
            text = "\n".join(str(x) for x in inputs if x)

        data = request_data if isinstance(request_data, dict) else {}
        if not data and isinstance(kwargs.get("data"), dict):
            data = kwargs["data"]

        # Always return inputs object when provided (LiteLLM maps .get("texts") back).
        if inputs is not None:
            passthrough: Any = inputs
        elif text is not None:
            passthrough = text
        elif args:
            passthrough = args[0]
        else:
            passthrough = {"texts": []}

        if not text or not PROMPT_IO_ENABLED:
            return passthrough

        call_id = _call_id_from_data(data) if data else None
        path = "/analyze/response" if input_type == "response" else "/analyze/prompt"
        payload: dict[str, Any] = {
            "prompt": text if isinstance(text, str) else str(text),
            "call_id": call_id,
            "model": _model_from_data(data) if data else None,
        }
        if input_type == "response":
            # Response path may only have output text; still post for metrics.
            payload["response"] = payload["prompt"]
            payload["prompt"] = _extract_text_from_messages(data.get("messages")) if data else ""

        scan = await self._post_scan(path, payload)
        phase = "post_call" if input_type == "response" else "during_call"
        if scan and data:
            _stamp_metadata(data, scan, phase=phase)
        if self.block_on_flag and scan and scan.get("flagged"):
            raise ValueError(
                f"hybrid_prompt_io blocked ({phase}, call_id={call_id}): "
                f"{(scan.get('messages') or ['flagged'])[0]}"
            )
        return passthrough

    async def _post_scan(self, path: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not PROMPT_IO_ENABLED:
            return None
        url = f"{self.api_base}{path}"
        t0 = time.perf_counter()
        try:
            client = get_async_httpx_client(
                llm_provider=httpxSpecialProvider.LoggingCallback
            )
            resp = await client.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data.setdefault("elapsed_ms", round((time.perf_counter() - t0) * 1000.0, 3))
                return data
        except Exception as exc:  # noqa: BLE001 — fail-open
            verbose_proxy_logger.debug(
                "hybrid_prompt_io scan fail-open path=%s err=%s", path, exc
            )
            return {
                "status": "timeout_or_error",
                "flagged": False,
                "messages": [],
                "results": {},
                "errors": [type(exc).__name__],
                "call_id": payload.get("call_id"),
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "service": "hybrid_prompt_io_guardrail",
            }
        return None

    async def async_moderation_hook(
        self,
        data: dict,
        user_api_key_dict: UserAPIKeyAuth,
        call_type: Literal[
            "completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
    ):
        """Parallel with LLM (during_call). Input-only; fail-open by default."""
        if call_type not in ("completion",):
            return
        prompt = _extract_text_from_messages(data.get("messages"))
        if not prompt:
            return
        call_id = _call_id_from_data(data)
        scan = await self._post_scan(
            "/analyze/prompt",
            {
                "prompt": prompt,
                "call_id": call_id,
                "model": _model_from_data(data),
            },
        )
        if not scan:
            return
        _stamp_metadata(data, scan, phase="during_call")
        verbose_proxy_logger.debug(
            "hybrid_prompt_io during_call call_id=%s flagged=%s",
            call_id,
            scan.get("flagged"),
        )
        if self.block_on_flag and scan.get("flagged"):
            raise ValueError(
                f"hybrid_prompt_io blocked prompt (call_id={call_id}): "
                f"{(scan.get('messages') or ['flagged'])[0]}"
            )

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
    ):
        """Audit response after LLM (post_call). Streaming = audit-only after assemble."""
        prompt = _extract_text_from_messages(data.get("messages"))
        resp_text = _response_text(response)
        if not prompt and not resp_text:
            return
        call_id = _call_id_from_data(data)
        scan = await self._post_scan(
            "/analyze/response",
            {
                "prompt": prompt,
                "response": resp_text,
                "call_id": call_id,
                "model": _model_from_data(data),
            },
        )
        if not scan:
            return
        _stamp_metadata(data, scan, phase="post_call")
        verbose_proxy_logger.debug(
            "hybrid_prompt_io post_call call_id=%s flagged=%s",
            call_id,
            scan.get("flagged"),
        )
        if self.block_on_flag and scan.get("flagged"):
            raise ValueError(
                f"hybrid_prompt_io blocked response (call_id={call_id}): "
                f"{(scan.get('messages') or ['flagged'])[0]}"
            )

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Optional[CallTypes],
    ) -> Optional[Union[Exception, str, dict]]:
        # Identity passthrough — scanning is parallel in moderation + post hooks.
        return data


# LiteLLM may reference the class path; instance not required for guardrails.
