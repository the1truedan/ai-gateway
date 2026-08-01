#!/usr/bin/env python3
"""ctx history-source plugin: export Grok Build sessions as ctx-history-jsonl-v1."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse the shared parser from the Open WebUI import tooling.
IMPORT_DIR = Path(__file__).resolve().parents[2] / "import"
sys.path.insert(0, str(IMPORT_DIR))

from grok_build_parser import discover_sessions, parse_session  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_cursor() -> dict:
    cursor_text = os.environ.get("CTX_HISTORY_CURSOR")
    cursor_file = os.environ.get("CTX_HISTORY_CURSOR_FILE")
    if not cursor_text and cursor_file and Path(cursor_file).exists():
        cursor_text = Path(cursor_file).read_text(encoding="utf-8")
    if not cursor_text:
        return {"sessions": {}}
    try:
        return json.loads(cursor_text)
    except json.JSONDecodeError:
        return {"sessions": {}}


def _session_mtime(session_dir: Path) -> float:
    updates = session_dir / "updates.jsonl"
    if updates.exists():
        return updates.stat().st_mtime
    summary = session_dir / "summary.json"
    if summary.exists():
        return summary.stat().st_mtime
    return session_dir.stat().st_mtime


def main() -> int:
    sessions_root = Path(
        os.environ.get("GROK_SESSIONS_DIR", str(Path.home() / ".grok" / "sessions"))
    )
    cwd_filter_raw = os.environ.get("GROK_BUILD_CWD_FILTER", "")
    cwd_filter = [p for p in cwd_filter_raw.split(":") if p] or None
    source_id = os.environ.get("CTX_HISTORY_SOURCE_ID", "default")
    provider_key = os.environ.get("CTX_HISTORY_PROVIDER_KEY", "grok-build")
    source_format = os.environ.get("CTX_HISTORY_SOURCE_FORMAT", "grok-build-updates-jsonl-v1")
    cursor_stream = os.environ.get("CTX_HISTORY_CURSOR_STREAM", f"{provider_key}:{source_id}")
    machine_id = os.environ.get("CTX_HISTORY_MACHINE_ID", "local")
    full_rescan = os.environ.get("CTX_HISTORY_FULL_RESCAN", "0") == "1"

    cursor = {"sessions": {}} if full_rescan else _load_cursor()
    known = cursor.setdefault("sessions", {})

    print(json.dumps({"record_type": "manifest", "schema_version": "ctx-history-jsonl-v1"}))

    exported = 0
    event_index_by_session: dict[str, int] = {}

    for session_dir in discover_sessions(sessions_root, cwd_filter=cwd_filter):
        session_key = str(session_dir)
        mtime = _session_mtime(session_dir)
        prev = known.get(session_key)
        if not full_rescan and prev and float(prev.get("mtime", 0)) >= mtime:
            continue

        session = parse_session(session_dir, include_tools=True, max_tool_chars=300)
        if session is None:
            known[session_key] = {"mtime": mtime}
            continue

        print(
            json.dumps(
                {
                    "record_type": "session",
                    "source_id": source_id,
                    "session_id": session.session_id,
                    "native_session_id": session.session_id,
                    "cwd": session.cwd,
                    "started_at": datetime.fromtimestamp(session.created_at, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "ended_at": datetime.fromtimestamp(session.updated_at, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "agent_type": "primary",
                    "role_hint": "developer",
                    "is_primary": True,
                    "status": "completed",
                    "metadata": {
                        "title": session.title,
                        "model": session.model_id,
                        "source_path": str(session_dir),
                    },
                }
            )
        )

        event_index = 0
        for msg in session.messages:
            preview = msg.content[:240]
            print(
                json.dumps(
                    {
                        "record_type": "event",
                        "source_id": source_id,
                        "session_id": session.session_id,
                        "event_index": event_index,
                        "event_id": f"{session.session_id}:{event_index}",
                        "native_cursor": f"{session_key}:{event_index}",
                        "event_type": "message",
                        "role": msg.role,
                        "occurred_at": datetime.fromtimestamp(msg.timestamp, tz=timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "payload": {"text": msg.content},
                        "preview": preview,
                        "metadata": {"provider": provider_key},
                    }
                )
            )
            event_index += 1

        known[session_key] = {"mtime": mtime, "events": event_index}
        exported += 1

    cursor["sessions"] = known
    print(
        json.dumps(
            {
                "record_type": "source",
                "source_id": source_id,
                "provider_key": provider_key,
                "source_format": source_format,
                "raw_source_path": str(sessions_root),
                "observed_at": _utc_now(),
                "machine_id": machine_id,
                "cursor": {
                    "after": {
                        "stream": cursor_stream,
                        "cursor": json.dumps(cursor),
                        "observed_at": _utc_now(),
                    }
                },
                "metadata": {"exported_sessions": exported},
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())