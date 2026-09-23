"""Push small markdown digests into an Open WebUI Knowledge collection and attach it to a model preset.

Part of the History Analyst setup (docs/HISTORY_ANALYST.md). Push metadata digests only
(session IDs, titles, counts), never raw transcripts.

Auth: OWUI API key from $OWUI_API_KEY, else the macOS Keychain item named by
$OWUI_KEYCHAIN_SERVICE (default `owui-api`). Open WebUI needs
Admin > Settings > General > "Enable API Keys" on, then a key from Settings > Account.

Re-pushing a file with the same name replaces the old copy in the collection.

  from owui_knowledge import OwuiKnowledge
  owui = OwuiKnowledge()
  res = owui.push("Session audits", "Weekly session audits", Path("audit.md"))
  owui.attach("history-analyst", res["knowledge_id"], "Session audits", full_context=True)
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Any

OWUI_URL = os.environ.get("OWUI_URL", "http://localhost:3000")
KEYCHAIN_SERVICE = os.environ.get("OWUI_KEYCHAIN_SERVICE", "owui-api")


def api_key() -> str:
    key = os.environ.get("OWUI_API_KEY", "").strip()
    if key:
        return key
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                             capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "data", "files"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


class OwuiKnowledge:
    def __init__(self, base_url: str = OWUI_URL, key: str | None = None, opener=urllib.request.urlopen):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.key = key if key is not None else api_key()
        if not self.key:
            raise RuntimeError(f"no OWUI API key: set OWUI_API_KEY or Keychain item {KEYCHAIN_SERVICE!r}")
        self._open = opener

    def _req(self, method: str, path: str, body: bytes | None = None, ctype: str = "application/json") -> Any:
        headers = {"Authorization": f"Bearer {self.key}"}
        if body is not None:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        with self._open(req, timeout=300) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None

    def _json(self, method: str, path: str, obj: dict[str, Any]) -> Any:
        return self._req(method, path, json.dumps(obj).encode())

    def ensure_collection(self, name: str, description: str) -> str:
        for k in _items(self._req("GET", "/knowledge/")):
            if k.get("name") == name:
                return k["id"]
        return self._json("POST", "/knowledge/create", {"name": name, "description": description})["id"]

    def _upload(self, path: Path) -> str:
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
                f"Content-Type: text/markdown\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        res = self._req("POST", "/files/?process=true&process_in_background=false", body,
                        f"multipart/form-data; boundary={boundary}")
        return res["id"]

    def push(self, collection: str, description: str, path: Path) -> dict[str, str]:
        kid = self.ensure_collection(collection, description)
        for f in _items(self._req("GET", f"/knowledge/{kid}/files")):
            if (f.get("filename") or (f.get("meta") or {}).get("name")) == path.name:
                self._json("POST", f"/knowledge/{kid}/file/remove", {"file_id": f["id"]})
        fid = self._upload(path)
        self._json("POST", f"/knowledge/{kid}/file/add", {"file_id": fid})
        return {"knowledge_id": kid, "file_id": fid, "name": path.name}

    def attach(self, model_id: str, knowledge_id: str, name: str, description: str = "",
               full_context: bool = False) -> bool:
        """Add a collection to a model preset's meta.knowledge. Returns False if already attached as asked.

        full_context=True sets the entry's context to "full" so Open WebUI injects the whole document
        instead of the top-k RAG chunks (for small digests that must be answered as a complete list).
        """
        model = self._req("GET", f"/models/model?id={model_id}")
        meta = dict(model.get("meta") or {})
        entry = {"id": knowledge_id, "name": name, "description": description, "type": "collection"}
        if full_context:
            entry["context"] = "full"
        knowledge = list(meta.get("knowledge") or [])
        existing = next((k for k in knowledge if k.get("id") == knowledge_id), None)
        if existing is not None and existing.get("context") == entry.get("context"):
            return False
        knowledge = [k for k in knowledge if k.get("id") != knowledge_id] + [entry]
        meta["knowledge"] = knowledge
        form = {k: model.get(k) for k in ("id", "base_model_id", "name", "params", "access_grants", "is_active")}
        form["meta"] = meta
        self._json("POST", "/models/model/update", form)
        return True
