#!/usr/bin/env python3
"""Parse Grok Build / Grok Code session files under ~/.grok/sessions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote

INVALID_RE = re.compile(r"[\ue000-\uf8ff]")


def sanitize_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return INVALID_RE.sub("", text)


def parse_iso_timestamp(value: Any, default: float | None = None) -> float:
    if isinstance(value, (int, float)):
        # Grok session records often use epoch seconds; agentTimestampMs is ms.
        if value > 1_000_000_000_000:
            return float(value) / 1000.0
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return default if default is not None else datetime.now(timezone.utc).timestamp()


def decode_cwd(encoded_dir: str) -> str:
    return unquote(encoded_dir)


@dataclass
class GrokBuildMessage:
    role: str
    content: str
    timestamp: float


@dataclass
class GrokBuildSession:
    session_id: str
    cwd: str
    title: str
    created_at: float
    updated_at: float
    model_id: str
    session_dir: Path
    messages: list[GrokBuildMessage] = field(default_factory=list)


def _chunk_text(update: dict[str, Any]) -> str:
    content = update.get("content") or {}
    if isinstance(content, dict):
        return sanitize_text(content.get("text") or "")
    return ""


def _tool_summary(update: dict[str, Any], max_chars: int) -> str:
    title = sanitize_text(update.get("title") or update.get("kind") or "tool")
    locations = update.get("locations") or []
    paths = []
    for loc in locations:
        if isinstance(loc, dict) and loc.get("path"):
            paths.append(str(loc["path"]))
    suffix = ""
    if paths:
        suffix = f" — `{paths[0]}`"
        if len(paths) > 1:
            suffix += f" (+{len(paths) - 1} more)"
    line = f"- **{title}**{suffix}"
    if len(line) > max_chars:
        return line[: max_chars - 3] + "..."
    return line


def parse_updates_jsonl(
    path: Path,
    *,
    include_tools: bool = False,
    max_tool_chars: int = 500,
    max_message_chars: int = 200_000,
) -> list[GrokBuildMessage]:
    if not path.exists():
        return []

    pending_user = ""
    pending_agent = ""
    pending_tools: list[str] = []
    messages: list[GrokBuildMessage] = []
    last_ts = path.stat().st_mtime

    def flush_turn() -> None:
        nonlocal pending_user, pending_agent, pending_tools
        if pending_user.strip():
            text = pending_user.strip()
            if len(text) > max_message_chars:
                text = text[: max_message_chars - 40] + "\n\n… [truncated for import]"
            messages.append(GrokBuildMessage("user", text, last_ts))
            pending_user = ""
        if include_tools and pending_tools:
            tool_blob = "_Tools:_\n" + "\n".join(pending_tools)
            messages.append(GrokBuildMessage("assistant", tool_blob, last_ts))
            pending_tools = []
        if pending_agent.strip():
            text = pending_agent.strip()
            if len(text) > max_message_chars:
                text = text[: max_message_chars - 40] + "\n\n… [truncated for import]"
            messages.append(GrokBuildMessage("assistant", text, last_ts))
            pending_agent = ""

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue

            params = record.get("params") or {}
            update = params.get("update") or {}
            meta = record.get("_meta") or params.get("_meta") or {}
            if meta.get("agentTimestampMs"):
                last_ts = parse_iso_timestamp(meta["agentTimestampMs"], last_ts)
            elif record.get("timestamp"):
                last_ts = parse_iso_timestamp(record["timestamp"], last_ts)

            kind = update.get("sessionUpdate") or ""
            if kind == "user_message_chunk":
                pending_user += _chunk_text(update)
            elif kind == "agent_message_chunk":
                pending_agent += _chunk_text(update)
            elif kind == "agent_thought_chunk":
                continue
            elif kind == "tool_call_update" and include_tools:
                status = str(update.get("status") or "").lower()
                if status in {"completed", "complete"}:
                    pending_tools.append(_tool_summary(update, max_tool_chars))
            elif kind == "turn_completed":
                flush_turn()

    flush_turn()
    return messages


def load_summary(session_dir: Path) -> dict[str, Any]:
    summary_path = session_dir / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def discover_sessions(
    root: Path,
    *,
    cwd_filter: list[str] | None = None,
) -> Iterator[Path]:
    if not root.exists():
        return
    normalized_filters = [p.rstrip("/") for p in (cwd_filter or [])]
    for cwd_dir in sorted(root.iterdir()):
        if not cwd_dir.is_dir():
            continue
        cwd = decode_cwd(cwd_dir.name)
        if normalized_filters and not any(cwd == f or cwd.startswith(f + "/") for f in normalized_filters):
            continue
        for session_dir in sorted(cwd_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            if (session_dir / "updates.jsonl").exists():
                yield session_dir


def parse_session(
    session_dir: Path,
    *,
    include_tools: bool = False,
    max_tool_chars: int = 500,
    max_message_chars: int = 200_000,
) -> GrokBuildSession | None:
    summary = load_summary(session_dir)
    info = summary.get("info") or {}
    session_id = str(info.get("id") or session_dir.name)
    cwd = str(info.get("cwd") or decode_cwd(session_dir.parent.name))
    title = (
        summary.get("session_summary")
        or summary.get("generated_title")
        or f"Grok Build {session_id[:8]}"
    )
    created_at = parse_iso_timestamp(summary.get("created_at"), session_dir.stat().st_mtime)
    updated_at = parse_iso_timestamp(
        summary.get("updated_at") or summary.get("last_active_at"),
        created_at,
    )
    model_id = str(summary.get("current_model_id") or "grok-code-fast-1")
    messages = parse_updates_jsonl(
        session_dir / "updates.jsonl",
        include_tools=include_tools,
        max_tool_chars=max_tool_chars,
        max_message_chars=max_message_chars,
    )
    if not messages:
        return None
    return GrokBuildSession(
        session_id=session_id,
        cwd=cwd,
        title=str(title),
        created_at=created_at,
        updated_at=updated_at,
        model_id=model_id,
        session_dir=session_dir,
        messages=messages,
    )