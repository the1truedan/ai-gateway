#!/usr/bin/env python3
"""OpenAI-compatible, privacy-first multi-host orchestration gateway."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_VERSION = "0.2.0"
AUTO_MODEL = "manager-auto"
LOCAL_MODELS = frozenset(
    {
        AUTO_MODEL,
        "manager-plan",
        "manager-code",
        "manager-review",
        "manager-reason",
        "manager-research",
        "manager-vision",
        "manager-embed",
        "manager-phi-local",
    }
)
FREE_CLOUD_MODELS = frozenset({"manager-openrouter-free"})
PAID_CLOUD_MODELS = frozenset(
    {
        "manager-codex-paid",
        "manager-claude-paid",
        "manager-gemini-paid",
        "manager-grok-paid",
        "manager-mimo-paid",
        "manager-hf-paid",
    }
)
EXPERIMENTAL_CLOUD_MODELS = frozenset(
    {
        "manager-darkbloom-experimental",
        "manager-akashml-experimental",
        "manager-salad-experimental",
    }
)
DEFAULT_MODELS = (
    "manager-auto", "manager-plan", "manager-code", "manager-review",
    "manager-reason", "manager-research", "manager-vision", "manager-embed",
    "manager-phi-local", "manager-openrouter-free", "manager-codex-paid",
    "manager-claude-paid", "manager-gemini-paid", "manager-grok-paid",
    "manager-mimo-paid", "manager-hf-paid", "manager-darkbloom-experimental",
    "manager-akashml-experimental", "manager-salad-experimental",
)

PHI_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bpatient(?:'s|s)?\b",
        r"\bmedical records?\b",
        r"\bdiagnos(?:is|es|tic)\b",
        r"\bmedication(?:s| list)?\b",
        r"\bprotected health information\b",
        r"\bPHI\b",
        r"\bHIPAA\b",
        r"\bMRN\b",
        r"\bdate of birth\b",
        r"\bcaregiver\b",
    )
)
APPLE_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\bmacOS\b", r"\bMetal\b", r"\bCoreML\b", r"\bMLX\b", r"\bXcode\b")
)
NVIDIA_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\bCUDA\b", r"\bNVIDIA\b", r"\bTensorRT\b", r"\bvLLM\b")
)
VISION_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bOpenCV\b",
        r"\bOCR\b",
        r"\bimage (?:preprocessing|features?|edges?|resize|thumbnail)\b",
        r"\bcomputer vision\b",
    )
)
LIGHTWEIGHT_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\bquick\b", r"\blightweight\b", r"\bshort summary\b", r"\bsmall task\b")
)
EXECUTE_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bimplement(?:ation|ed|ing)?\b",
        r"\bcode\b",
        r"\bdebug\b",
        r"\bfix\b",
        r"\bbuild\b",
        r"\btest\b",
        r"\bbenchmark\b",
        r"\bdeploy\b",
    )
)
PLAN_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\bplan\b", r"\bdesign\b", r"\barchitect", r"\broadmap\b")
)
RECON_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\bresearch\b", r"\bcompare\b", r"\blatest\b", r"\bfind\b")
)
REASON_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (r"\breason\b", r"\banaly[sz]e\b", r"\bprove\b", r"\bcomplex\b")
)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _load_config() -> dict[str, Any]:
    path = Path(os.environ.get("ORCHESTRATOR_CONFIG", "/app/config/routes.json"))
    return json.loads(path.read_text(encoding="utf-8"))


CONFIG = _load_config()
HOSTS: dict[str, dict[str, Any]] = CONFIG["hosts"]
PAID_MODELS = frozenset(CONFIG.get("paid_models", PAID_CLOUD_MODELS))
EXPERIMENTAL_MODELS = frozenset(CONFIG.get("experimental_models", EXPERIMENTAL_CLOUD_MODELS))
FREE_CLOUD_MODEL = str(CONFIG.get("free_cloud_model", "manager-openrouter-free"))
FREE_CLOUD_HOST = str(CONFIG.get("free_cloud_host", "gpu-host"))
API_KEY = os.environ.get("ORCHESTRATOR_API_KEY", "")
UPSTREAM_KEY = os.environ.get("ORCHESTRATOR_UPSTREAM_KEY", "")
CAPACITY_TOKEN = os.environ.get("CAPACITY_AGENT_TOKEN", "")
TEST_CAPACITY = json.loads(os.environ.get("ORCHESTRATOR_TEST_CAPACITY", "{}"))
ALLOW_TEST_HEADERS = bool(TEST_CAPACITY)
TIMEOUT = float(os.environ.get("ORCHESTRATOR_UPSTREAM_TIMEOUT", "300"))
CAPACITY_TTL = float(os.environ.get("ORCHESTRATOR_CAPACITY_TTL", "5"))
GATEWAY_BASE_URL = str(CONFIG.get("gateway_base_url", "")).rstrip("/")
HOST_MODEL_MAP: dict[str, dict[str, str]] = CONFIG.get("host_model_map", {})
CATALOG_PATH = Path(os.environ.get("MANAGER_CATALOG_PATH", "")) if os.environ.get("MANAGER_CATALOG_PATH") else None

if not API_KEY and not _env_bool("ORCHESTRATOR_ALLOW_INSECURE"):
    raise RuntimeError("ORCHESTRATOR_API_KEY is required")


@dataclass(frozen=True)
class Decision:
    selected_host: str
    selected_model: str
    tier: str
    reason: str
    sensitive: bool = False
    cloud_allowed: bool = True
    paid_approved: bool = False

    def as_dict(self, route_id: str) -> dict[str, Any]:
        return {
            "route_id": route_id,
            "selected_host": self.selected_host,
            "selected_model": self.selected_model,
            "tier": self.tier,
            "reason": self.reason,
            "sensitive": self.sensitive,
            "cloud_allowed": self.cloud_allowed,
            "paid_approved": self.paid_approved,
        }


class CapacityCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, host: str) -> dict[str, Any]:
        if host in TEST_CAPACITY:
            return dict(TEST_CAPACITY[host])
        now = time.monotonic()
        with self._lock:
            cached = self._values.get(host)
            if cached and now - cached[0] < CAPACITY_TTL:
                return cached[1]
        value = self._fetch(host)
        with self._lock:
            self._values[host] = (now, value)
        return value

    def _fetch(self, host: str) -> dict[str, Any]:
        url = str(HOSTS[host].get("capacity_url", ""))
        if not url:
            return {"saturated": False, "score": 0.5, "available": True}
        headers = {"Authorization": f"Bearer {CAPACITY_TOKEN}"} if CAPACITY_TOKEN else {}
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.load(response)
            return {
                "saturated": bool(payload.get("saturated", False)),
                "score": float(payload.get("score", 0.5)),
                "available": True,
            }
        except (OSError, ValueError, urllib.error.URLError):
            return {"saturated": True, "score": 1.0, "available": False}


CAPACITY = CapacityCache()


def _public_models() -> tuple[str, ...]:
    """Expose only inventory entries that passed catalog validation."""
    if CATALOG_PATH:
        try:
            if not CATALOG_PATH.is_file():
                return DEFAULT_MODELS
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            names = tuple(
                str(item["name"])
                for item in catalog.get("models", [])
                if item.get("active") and str(item.get("name", "")).startswith("manager-")
            )
            if names:
                return names
        except (OSError, ValueError, KeyError):
            pass
    return DEFAULT_MODELS


def _message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in payload.get("messages", []):
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    request_input = payload.get("input")
    if isinstance(request_input, str):
        parts.append(request_input)
    elif isinstance(request_input, list):
        for item in request_input:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
    return "\n".join(parts)


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _is_sensitive(text: str, privacy: str) -> bool:
    if privacy.lower() in {"phi", "sensitive", "confidential", "privileged", "local"}:
        return True
    return _matches(PHI_PATTERNS, text)


def _role(text: str) -> str:
    if _matches(EXECUTE_PATTERNS, text):
        return "code"
    if _matches(RECON_PATTERNS, text):
        return "research"
    if _matches(PLAN_PATTERNS, text):
        return "plan"
    if _matches(REASON_PATTERNS, text):
        return "reason"
    return "code"


def _capacities(test_override: str) -> dict[str, dict[str, Any]]:
    values = {name: CAPACITY.get(name) for name in HOSTS}
    if ALLOW_TEST_HEADERS and test_override == "all-saturated":
        for value in values.values():
            value.update({"saturated": True, "score": 1.0})
    return values


def _local_host(
    text: str, values: dict[str, dict[str, Any]], *, allow_nas_host: bool = False
) -> str | None:
    order = ["gpu-host", "mac-client"]
    if allow_nas_host and _matches(VISION_PATTERNS, text):
        order = ["nas-host", "gpu-host", "mac-client"]
    elif allow_nas_host and _matches(LIGHTWEIGHT_PATTERNS, text):
        order = ["nas-host", "gpu-host", "mac-client"]
    elif _matches(APPLE_PATTERNS, text):
        order = ["mac-client", "gpu-host"]
    elif _matches(NVIDIA_PATTERNS, text):
        order = ["gpu-host", "mac-client"]
    else:
        order = sorted(order, key=lambda host: float(values.get(host, {}).get("score", 1.0)))
    for host in order:
        if host in HOSTS and not values.get(host, {}).get("saturated", True):
            return host
    return None


def decide(payload: dict[str, Any], headers: Any) -> Decision:
    text = _message_text(payload)
    privacy = headers.get("X-Manager-Privacy", "")
    sensitive = _is_sensitive(text, privacy)
    requested = str(payload.get("model") or AUTO_MODEL)
    values = _capacities(headers.get("X-Manager-Test-Capacity", ""))

    if requested not in DEFAULT_MODELS:
        raise ValueError("unknown_model")

    if requested in PAID_MODELS or requested in EXPERIMENTAL_MODELS:
        if sensitive:
            raise PermissionError("sensitive_cloud_blocked")
        return Decision(
            selected_host=FREE_CLOUD_HOST,
            selected_model=requested,
            tier="experimental-cloud" if requested in EXPERIMENTAL_MODELS else "paid-cloud",
            reason="explicit provider egress alias selected",
            paid_approved=True,
        )

    if sensitive or requested == "manager-phi-local":
        # NAS-HOST's small models are deliberately excluded from PHI routing.
        host = _local_host(text, values)
        if host is None:
            raise ConnectionError("sensitive_local_unavailable")
        return Decision(
            selected_host=host,
            selected_model="manager-phi-local",
            tier="local",
            reason="sensitive content is confined to a local-only alias",
            sensitive=True,
            cloud_allowed=False,
        )

    if requested != AUTO_MODEL:
        if requested in FREE_CLOUD_MODELS:
            return Decision(
                selected_host=FREE_CLOUD_HOST,
                selected_model=requested,
                tier="free-cloud",
                reason="explicit free-cloud alias selected",
            )
        host = _local_host(text, values, allow_nas_host=requested == "manager-vision")
        if host is None:
            raise RuntimeError("cloud_consent_required")
        return Decision(host, requested, "local", "explicit local manager alias selected", cloud_allowed=False)

    role = _role(text)
    host = _local_host(text, values, allow_nas_host=True)
    if host is None:
        raise RuntimeError("cloud_consent_required")
    if host == "nas-host" and _matches(VISION_PATTERNS, text):
        selected_model = "manager-vision"
    elif host == "nas-host":
        selected_model = "manager-code"
    else:
        selected_model = "manager-reason" if role == "plan" else f"manager-{role}"
    return Decision(
        selected_host=host,
        selected_model=selected_model,
        tier="local",
        reason=f"classified as {role}; selected available local host",
        cloud_allowed=False,
    )


def _upstream_url(decision: Decision, path: str) -> str:
    base = GATEWAY_BASE_URL or str(HOSTS[decision.selected_host]["base_url"]).rstrip("/")
    suffix = path[3:] if path.startswith("/v1") else path
    return f"{base}{suffix}"


def _upstream_model(decision: Decision) -> str:
    if decision.tier == "local":
        return HOST_MODEL_MAP.get(decision.selected_host, {}).get(
            decision.selected_model, decision.selected_model
        )
    return decision.selected_model


def _stamp_manager_metadata(
    payload: dict[str, Any], decision: Decision, route_id: str
) -> None:
    """Join manager routing and LiteLLM spend records without storing bodies."""
    caller_metadata = payload.get("metadata")
    metadata = dict(caller_metadata) if isinstance(caller_metadata, dict) else {}
    routing = {
        "manager_route_id": route_id,
        "manager_selected_host": decision.selected_host,
        "manager_selected_model": decision.selected_model,
        "manager_tier": decision.tier,
        "manager_provider_class": decision.tier,
    }
    workflow_id = payload.get("workflow_id") or metadata.get("manager_workflow_id")
    if workflow_id:
        routing["manager_workflow_id"] = str(workflow_id)
    metadata.update(routing)
    # LiteLLM persists this reserved sub-map in SpendLogs metadata. Keep the
    # flat keys too for callbacks and upstreams that consume request metadata.
    caller_spend_metadata = metadata.get("spend_logs_metadata")
    spend_metadata = (
        dict(caller_spend_metadata) if isinstance(caller_spend_metadata, dict) else {}
    )
    spend_metadata.update(routing)
    metadata["spend_logs_metadata"] = spend_metadata
    payload["metadata"] = metadata


class Handler(BaseHTTPRequestHandler):
    server_version = "manager-orchestrator/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if _env_bool("ORCHESTRATOR_ACCESS_LOG"):
            super().log_message(fmt, *args)

    def _authorized(self) -> bool:
        if not API_KEY:
            return True
        supplied = self.headers.get("Authorization", "")
        return supplied == f"Bearer {API_KEY}"

    def _json(self, status: int, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> tuple[bytes, dict[str, Any]]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size)
        return raw, json.loads(raw or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/healthz", "/readyz"}:
            self._json(200, {"status": "ok", "service": "manager-orchestrator", "version": APP_VERSION})
            return
        if not self._authorized():
            self._json(401, {"error": {"code": "unauthorized"}})
            return
        if self.path == "/v1/models":
            now = int(time.time())
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": model, "object": "model", "created": now, "owned_by": "manager"}
                        for model in _public_models()
                    ],
                },
            )
            return
        if self.path == "/metrics":
            body = b"manager_orchestrator_up 1\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"error": {"code": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(401, {"error": {"code": "unauthorized"}})
            return
        try:
            raw, payload = self._body()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": {"code": "invalid_json"}})
            return
        route_id = uuid.uuid4().hex
        try:
            decision = decide(payload, self.headers)
        except ValueError:
            self._json(404, {"error": {"code": "unknown_model"}})
            return
        except PermissionError:
            self._json(
                403,
                {
                    "error": {
                        "code": "sensitive_cloud_blocked",
                        "message": "Sensitive prompts cannot use cloud aliases",
                        "recommended_model": "manager-phi-local",
                    }
                },
            )
            return
        except ConnectionError:
            self._json(
                503,
                {
                    "error": {
                        "code": "sensitive_local_unavailable",
                        "message": "No local-only host is currently available",
                    }
                },
            )
            return
        except RuntimeError as error:
            if str(error) != "cloud_consent_required":
                raise
            self._json(
                409,
                {
                    "error": {
                        "code": "cloud_consent_required",
                        "message": "Local hosts are saturated; select a cloud tier explicitly",
                        "allowed_models": [
                            "manager-openrouter-free",
                            "manager-codex-paid",
                            "manager-claude-paid",
                            "manager-gemini-paid",
                            "manager-grok-paid",
                            "manager-mimo-paid",
                            "manager-hf-paid",
                        ],
                    }
                },
            )
            return

        if self.path == "/v1/router/decision":
            self._json(200, decision.as_dict(route_id))
            return
        if self.path not in {"/v1/chat/completions", "/v1/responses"}:
            self._json(404, {"error": {"code": "not_found"}})
            return
        payload["model"] = _upstream_model(decision)
        _stamp_manager_metadata(payload, decision, route_id)
        self._proxy(json.dumps(payload).encode(), decision, route_id)

    def _proxy(self, body: bytes, decision: Decision, route_id: str) -> None:
        url = urllib.parse.urlsplit(_upstream_url(decision, self.path))
        connection_cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        kwargs: dict[str, Any] = {"timeout": TIMEOUT}
        if url.scheme == "https":
            kwargs["context"] = ssl.create_default_context()
        connection = connection_cls(url.hostname, url.port, **kwargs)
        path = urllib.parse.urlunsplit(("", "", url.path, url.query, ""))
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {UPSTREAM_KEY}",
            "X-Manager-Route-Id": route_id,
            # Redundant standard LiteLLM correlation fields keep the route ID
            # queryable even on releases that regress arbitrary spend metadata.
            "X-LiteLLM-Agent-Id": route_id,
            "X-LiteLLM-Session-Id": route_id,
            # LiteLLM 1.92 persists this authenticated header in SpendLogs.
            # Do not include caller-controlled values here.
            "X-LiteLLM-Spend-Logs-Metadata": json.dumps(
                {
                    "manager_route_id": route_id,
                    "manager_selected_host": decision.selected_host,
                    "manager_selected_model": decision.selected_model,
                    "manager_tier": decision.tier,
                },
                separators=(",", ":"),
            ),
        }
        started = time.monotonic()
        response_committed = False
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            blocked = {"connection", "content-length", "transfer-encoding"}
            for name, value in response.getheaders():
                if name.lower() not in blocked:
                    self.send_header(name, value)
            self.send_header("X-Manager-Route-Id", route_id)
            self.send_header("X-Manager-Selected-Host", decision.selected_host)
            self.send_header("X-Manager-Selected-Model", decision.selected_model)
            self.send_header("X-Manager-Tier", decision.tier)
            self.send_header("X-Manager-Provider-Class", decision.tier)
            self.send_header("X-Manager-Selected-Worker", _upstream_model(decision))
            workflow_id = self.headers.get("X-Manager-Workflow-Id")
            if workflow_id:
                self.send_header("X-Manager-Workflow-Id", workflow_id)
            self.end_headers()
            response_committed = True
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException) as error:
            if not response_committed and not self.wfile.closed:
                self._json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": {"code": "upstream_unavailable", "message": str(error)}},
                    {"X-Manager-Route-Id": route_id},
                )
            else:
                self.close_connection = True
        finally:
            connection.close()
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            record = {
                "route_id": route_id,
                "prompt_hash": hashlib.sha256(body).hexdigest()[:16],
                "selected_host": decision.selected_host,
                "selected_model": decision.selected_model,
                "tier": decision.tier,
                "elapsed_ms": elapsed_ms,
            }
            print(json.dumps(record, separators=(",", ":")), flush=True)


def main() -> None:
    host = os.environ.get("ORCHESTRATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8790"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
