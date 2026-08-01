#!/usr/bin/env python3
"""Merge gpu-host worker LiteLLM config with free-cloud + optional paid aliases.

NEW LAW: gpu-host may use cloud compute (mock-tua overflow, free/paid explicit).
PHI never auto-routes cloud — orchestrator/NARC still gate manager-phi-local.

Writes litellm_config.linux.merged.yaml for docker mount.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "litellm_config.linux.yaml"
FREE = ROOT / "openrouter_free_models.generated.yaml"
OUT = ROOT / "litellm_config.linux.merged.yaml"

# Paid / experimental aliases (keys from env; only registered when key may exist)
PAID_STUBS = [
    {
        "model_name": "manager-grok-paid",
        "litellm_params": {
            "model": "xai/grok-3-mini",
            "api_key": "os.environ/XAI_API_KEY",
        },
    },
    {
        "model_name": "manager-gemini-paid",
        "litellm_params": {
            "model": "gemini/gemini-2.0-flash",
            "api_key": "os.environ/GEMINI_API_KEY",
        },
    },
    {
        "model_name": "manager-hf-paid",
        "litellm_params": {
            "model": "huggingface/meta-llama/Meta-Llama-3-8B-Instruct",
            "api_key": "os.environ/HF_TOKEN",
        },
    },
    {
        "model_name": "manager-claude-paid",
        "litellm_params": {
            "model": "anthropic/claude-3-5-haiku-20241022",
            "api_key": "os.environ/ANTHROPIC_API_KEY",
        },
    },
    {
        "model_name": "manager-codex-paid",
        "litellm_params": {
            "model": "openai/gpt-4o-mini",
            "api_key": "os.environ/OPENAI_API_KEY",
        },
    },
]


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    # Minimal fallback without PyYAML: only used if stdlib-only host
    return {"_raw": text}


def _extract_model_blocks(raw: str) -> list[str]:
    """Split raw YAML into model_list item text blocks (best-effort)."""
    if "model_list:" not in raw:
        return []
    body = raw.split("model_list:", 1)[1]
    # cut off settings sections
    for stop in ("litellm_settings:", "router_settings:", "general_settings:"):
        if stop in body:
            body = body.split(stop, 1)[0]
    blocks: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.startswith("  - model_name:"):
            if current:
                blocks.append("\n".join(current).rstrip() + "\n")
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append("\n".join(current).rstrip() + "\n")
    return blocks


def merge(worker: dict, free: dict, *, include_paid: bool) -> dict:
    models: list = []
    seen: set[str] = set()

    def add_all(items: list | None) -> None:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            name = item.get("model_name")
            if not name or name in seen:
                continue
            seen.add(str(name))
            models.append(item)

    add_all(worker.get("model_list"))
    add_all(free.get("model_list"))
    if include_paid:
        add_all(PAID_STUBS)

    out = {
        "model_list": models,
        "litellm_settings": worker.get("litellm_settings")
        or {
            "callbacks": ["prometheus"],
            "drop_params": True,
            "telemetry": False,
            "store_prompts_in_spend_logs": False,
        },
        "router_settings": worker.get("router_settings") or {"num_retries": 0, "fallbacks": []},
        "general_settings": worker.get("general_settings")
        or {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "database_url": "os.environ/DATABASE_URL",
        },
    }
    return out


def _render_without_yaml(*, include_paid: bool) -> tuple[str, int]:
    """Concatenate model_list blocks when PyYAML is unavailable."""
    worker_raw = WORKER.read_text(encoding="utf-8") if WORKER.is_file() else ""
    free_raw = FREE.read_text(encoding="utf-8") if FREE.is_file() else ""
    blocks = _extract_model_blocks(worker_raw) + _extract_model_blocks(free_raw)
    seen: set[str] = set()
    unique: list[str] = []
    for b in blocks:
        m = re.search(r"model_name:\s*(\S+)", b)
        name = m.group(1) if m else None
        if name and name in seen:
            continue
        if name:
            seen.add(name)
        unique.append(b if b.endswith("\n") else b + "\n")
    if include_paid:
        for stub in PAID_STUBS:
            name = stub["model_name"]
            if name in seen:
                continue
            seen.add(name)
            params = stub["litellm_params"]
            unique.append(
                f"  - model_name: {name}\n"
                f"    litellm_params:\n"
                f"      model: {params['model']}\n"
                f"      api_key: {params['api_key']}\n"
            )
    settings = """litellm_settings:
  callbacks: [prometheus]
  drop_params: true
  telemetry: false
  store_prompts_in_spend_logs: false
router_settings: {num_retries: 0, fallbacks: []}
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
"""
    body = "model_list:\n" + "".join(unique) + settings
    return body, len(unique)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-paid", action="store_true", help="Skip paid stubs")
    parser.add_argument("-o", "--output", type=Path, default=OUT)
    args = parser.parse_args()

    header = (
        f"# AUTO-MERGED — do not edit by hand\n"
        f"# generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"# sources: litellm_config.linux.yaml + openrouter_free_models.generated.yaml"
        f"{'' if args.no_paid else ' + paid stubs'}\n"
    )

    if yaml is None:
        body, count = _render_without_yaml(include_paid=not args.no_paid)
        header += f"# model_count: {count}\n# note: rendered without PyYAML\n"
        args.output.write_text(header + body, encoding="utf-8")
        print(f"wrote {args.output} models={count}")
        return 0

    worker = _load(WORKER)
    free = _load(FREE)
    # If fallback raw-only load happened
    if "_raw" in worker or "_raw" in free:
        body, count = _render_without_yaml(include_paid=not args.no_paid)
        header += f"# model_count: {count}\n"
        args.output.write_text(header + body, encoding="utf-8")
        print(f"wrote {args.output} models={count}")
        return 0

    merged = merge(worker, free, include_paid=not args.no_paid)
    header += f"# model_count: {len(merged['model_list'])}\n"
    body = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)
    # LiteLLM expects os.environ/KEY as unquoted in some parsers — keep as plain strings
    body = re.sub(r"api_key: 'os\.environ/([^']+)'", r"api_key: os.environ/\1", body)
    body = re.sub(r'api_key: "os\.environ/([^"]+)"', r"api_key: os.environ/\1", body)
    body = re.sub(r"master_key: 'os\.environ/([^']+)'", r"master_key: os.environ/\1", body)
    body = re.sub(r"database_url: 'os\.environ/([^']+)'", r"database_url: os.environ/\1", body)
    args.output.write_text(header + body, encoding="utf-8")
    print(f"wrote {args.output} models={len(merged['model_list'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
