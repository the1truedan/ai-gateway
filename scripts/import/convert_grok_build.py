#!/usr/bin/env python3
"""Convert Grok Build / Grok Code sessions to open-webui JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from grok_build_parser import discover_sessions, parse_session, sanitize_text

DEFAULT_SESSIONS_ROOT = Path.home() / ".grok" / "sessions"
SUBDIR = "grok-build"
DEFAULT_MODEL = os.environ.get("OPENWEBUI_GROK_MODEL", "xai/grok-code-fast-1")
DEFAULT_MODEL_NAME = os.environ.get("OPENWEBUI_GROK_MODEL_NAME", "Grok Code")


def extract_last_sentence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    matches = re.findall(r"[^.!?]*[.!?]", cleaned, flags=re.DOTALL)
    if matches:
        return matches[-1].strip()
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    return lines[-1] if lines else cleaned


def slugify(text: str) -> str:
    text = re.sub(r"\s+", "_", text.strip())
    text = re.sub(r"[^a-zA-Z0-9_\-]", "", text)
    return text[:50] or "chat"


def model_for_session(model_id: str) -> tuple[str, str]:
    if "composer" in model_id or "code" in model_id or "grok" in model_id:
        return DEFAULT_MODEL, DEFAULT_MODEL_NAME
    return DEFAULT_MODEL, DEFAULT_MODEL_NAME


def build_webui(session, user_id: str) -> dict[str, Any]:
    model, model_name = model_for_session(session.model_id)
    messages_map: dict[str, Any] = {}
    messages_list: list[dict[str, Any]] = []
    prev_id: str | None = None

    for msg in session.messages:
        msg_id = str(uuid.uuid4())
        clean = sanitize_text(msg.content)
        entry: dict[str, Any] = {
            "id": msg_id,
            "parentId": prev_id,
            "childrenIds": [],
            "role": msg.role,
            "content": clean,
            "timestamp": int(msg.timestamp),
        }
        if msg.role == "user":
            entry["models"] = [model]
        else:
            entry.update(
                {
                    "model": model,
                    "modelName": model_name,
                    "modelIdx": 0,
                    "userContext": None,
                    "lastSentence": extract_last_sentence(clean),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "done": True,
                }
            )
        if prev_id:
            messages_map[prev_id]["childrenIds"].append(msg_id)
        messages_map[msg_id] = entry
        messages_list.append(entry)
        prev_id = msg_id

    return {
        "id": "",
        "title": session.title,
        "models": [model],
        "params": {"source": "grok-build", "cwd": session.cwd, "session_id": session.session_id},
        "history": {"messages": messages_map, "currentId": prev_id},
        "messages": messages_list,
        "tags": [],
        "timestamp": int(session.updated_at * 1000),
        "files": [],
        "userId": user_id,
    }


def convert_sessions(
    sessions_root: Path,
    user_id: str,
    outdir: Path,
    *,
    cwd_filter: list[str] | None,
    include_tools: bool,
) -> int:
    outdir = outdir / SUBDIR
    outdir.mkdir(parents=True, exist_ok=True)
    converted = 0
    for session_dir in discover_sessions(sessions_root, cwd_filter=cwd_filter):
        session = parse_session(session_dir, include_tools=include_tools)
        if session is None:
            continue
        webui = build_webui(session, user_id)
        fname = f"{slugify(session.title)}_{session.session_id}.json"
        with (outdir / fname).open("w", encoding="utf-8") as handle:
            json.dump(webui, handle, ensure_ascii=False, indent=2)
        converted += 1
        print(f"converted {session.session_id} -> {fname} ({len(session.messages)} messages)")
    return converted


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Convert Grok Build sessions to open-webui JSON")
    parser.add_argument(
        "--sessions-root",
        default=str(DEFAULT_SESSIONS_ROOT),
        help="Grok sessions root (default: ~/.grok/sessions)",
    )
    parser.add_argument("--userid", required=True, help="Open WebUI user ID")
    parser.add_argument("--output-dir", default="output", help="Directory for output JSON files")
    parser.add_argument(
        "--cwd-filter",
        action="append",
        default=[],
        help="Only import sessions whose cwd matches (repeatable)",
    )
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Include completed tool calls as assistant notes",
    )
    args = parser.parse_args()

    count = convert_sessions(
        Path(args.sessions_root),
        args.userid,
        Path(args.output_dir),
        cwd_filter=args.cwd_filter or None,
        include_tools=args.include_tools,
    )
    if count == 0:
        print("No Grok Build sessions converted", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_cli()