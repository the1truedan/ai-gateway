#!/usr/bin/env python3
"""Refresh LiteLLM OpenRouter entries from zero-cost models on OpenRouter.

Source of truth: https://openrouter.ai/api/v1/models
Web filter equivalent: https://openrouter.ai/models?max_price=0

Run manually or on a 24h schedule. Safe to re-run; only free models are emitted.
Also writes litellm_data/openrouter_free_catalog.json and
config/clients/openrouter-free-models.md (catalog table + compare guide).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://openrouter.ai/api/v1/models"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_YAML = ROOT / "openrouter_free_models.generated.yaml"
DEFAULT_CATALOG = ROOT / "litellm_data" / "openrouter_free_catalog.json"
DEFAULT_MARKDOWN = ROOT / "config" / "clients" / "openrouter-free-models.md"

# Skip non-chat modalities for this coding/audit gateway
SKIP_ID_SUBSTRINGS = (
    "stealth/",   # cloaked previews: prompts shared upstream; bill when they exit stealth
    "lyria",
    "clip-preview",
    "content-safety",
)

CURATED = {
    "manager-audit-claude": "poolside/laguna-xs-2.1:free",
    "manager-openrouter-free": "openrouter/free",
}

# One-line roles for the human guide (id → use)
ROLE_HINTS = {
    "qwen/qwen3-coder:free": "Best free coding + huge context audits",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "Frontier reasoning / orchestration",
    "nvidia/nemotron-3-super-120b-a12b:free": "Strong general MoE, efficient active params",
    "poolside/laguna-m.1:free": "Flagship free coding agent",
    "poolside/laguna-xs-2.1:free": "Lighter coding agent (curated audit)",
    "cohere/north-mini-code:free": "Agentic coding (North family)",
    "qwen/qwen3-next-80b-a3b-instruct:free": "Fast instruct chat",
    "google/gemma-4-31b-it:free": "Free multimodal VLM (image/video→text)",
    "google/gemma-4-26b-a4b-it:free": "Free multimodal MoE VLM",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": "Multimodal perception / sub-agent",
    "nvidia/nemotron-3-nano-30b-a3b:free": "Efficient small MoE for agents",
    "openrouter/free": "Router: random free model (unpredictable)",
    "openai/gpt-oss-20b:free": "Small OSS baseline",
    "meta-llama/llama-3.3-70b-instruct:free": "General chat 70B",
    "meta-llama/llama-3.2-3b-instruct:free": "Tiny general chat",
    "nousresearch/hermes-3-llama-3.1-405b:free": "Large generalist / agentic",
    "nvidia/nemotron-nano-12b-v2-vl:free": "Video/image VL reasoning",
    "nvidia/nemotron-nano-9b-v2:free": "Tiny efficient LLM",
    "tencent/hy3:free": "Large MoE reasoning (Tencent)",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "Uncensored; avoid PHI",
}


def slugify(model_id: str) -> str:
    s = model_id.lower()
    s = s.replace("/", "-").replace(":", "-").replace(".", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return f"or-free-{s}"


def fetch_models(api_key: str) -> list[dict]:
    req = Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://ai-gateway.local",
            "X-Title": "ai-gateway",
        },
    )
    with urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    return payload.get("data", [])


def is_free(model: dict) -> bool:
    pricing = model.get("pricing") or {}
    try:
        prompt = float(pricing.get("prompt", 1) or 0)
        completion = float(pricing.get("completion", 1) or 0)
        request = float(pricing.get("request", 0) or 0)
        image = float(pricing.get("image", 0) or 0)
    except (TypeError, ValueError):
        return False
    return prompt == 0 and completion == 0 and request == 0 and image == 0


def is_chat_candidate(model: dict) -> bool:
    model_id = (model.get("id") or "").lower()
    if any(x in model_id for x in SKIP_ID_SUBSTRINGS):
        return False
    arch = model.get("architecture") or {}
    modality = (arch.get("modality") or "").lower()
    if modality and "text" not in modality and "image->text" not in modality:
        return False
    return True


def rank_key(model: dict) -> tuple:
    model_id = model.get("id", "")
    ctx = int(model.get("context_length") or 0)
    curated_bonus = 0
    if model_id in CURATED.values():
        curated_bonus = 10_000_000
    if ":free" in model_id or model_id == "openrouter/free":
        curated_bonus += 1_000_000
    if any(k in model_id for k in ("coder", "instruct", "reasoning", "laguna", "nemotron")):
        curated_bonus += 100_000
    return (curated_bonus, ctx, model_id)


def modality_of(model: dict) -> str:
    arch = model.get("architecture") or {}
    return (arch.get("modality") or "text->text") or "text->text"


def trunc_desc(model: dict, limit: int = 160) -> str:
    desc = (model.get("description") or "").replace("\n", " ").strip()
    if len(desc) <= limit:
        return desc
    return desc[: limit - 1].rstrip() + "…"


def build_entries(models: list[dict]) -> list[dict]:
    free = [m for m in models if is_free(m) and is_chat_candidate(m)]
    free.sort(key=rank_key, reverse=True)

    by_id = {m["id"]: m for m in free}
    entries: list[dict] = []
    used_names: set[str] = set()

    def add_entry(model_id: str, model_name: str | None = None) -> None:
        if model_id not in by_id:
            return
        name = model_name or slugify(model_id)
        if name in used_names:
            return
        used_names.add(name)
        entries.append(
            {
                "model_name": name,
                "litellm_params": {
                    "model": f"openrouter/{model_id}",
                    "api_key": "os.environ/OPENROUTER_API_KEY",
                },
            }
        )

    for alias, model_id in CURATED.items():
        add_entry(model_id, alias)

    for model in free:
        add_entry(model["id"])

    return entries


def render_yaml(entries: list[dict], generated_at: str, count: int) -> str:
    lines = [
        "# AUTO-GENERATED — do not edit by hand",
        f"# generated_at: {generated_at}",
        f"# free_model_count: {count}",
        "# source: https://openrouter.ai/api/v1/models (max_price=0 filter)",
        "model_list:",
    ]
    for entry in entries:
        lines.append(f"  - model_name: {entry['model_name']}")
        lines.append("    litellm_params:")
        lines.append(f"      model: {entry['litellm_params']['model']}")
        lines.append(f"      api_key: {entry['litellm_params']['api_key']}")
    lines.append("")
    return "\n".join(lines)


def fmt_ctx(n: int | None) -> str:
    if not n:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n // 1000}k"
    return str(n)


def role_for(model_id: str) -> str:
    if model_id in ROLE_HINTS:
        return ROLE_HINTS[model_id]
    if "coder" in model_id or "code" in model_id:
        return "Coding-oriented free model"
    if "vl" in model_id or "vision" in model_id:
        return "Multimodal / vision free model"
    if "reasoning" in model_id:
        return "Reasoning free model"
    return "General free chat"


def write_catalog(path: Path, models: list[dict], entries: list[dict], generated_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    free_sorted = sorted(models, key=rank_key, reverse=True)
    alias_by_upstream: dict[str, list[str]] = {}
    for e in entries:
        upstream = e["litellm_params"]["model"].removeprefix("openrouter/")
        alias_by_upstream.setdefault(upstream, []).append(e["model_name"])

    catalog = {
        "generated_at": generated_at,
        "source_url": "https://openrouter.ai/models?max_price=0",
        "api_url": API_URL,
        "free_model_count": len(models),
        "litellm_alias_count": len(entries),
        "curated_defaults": CURATED,
        "models": [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "context_length": m.get("context_length"),
                "modality": modality_of(m),
                "description": trunc_desc(m, 240),
                "litellm_aliases": alias_by_upstream.get(m.get("id") or "", [slugify(m["id"])]),
                "role": role_for(m.get("id") or ""),
            }
            for m in free_sorted
        ],
    }
    path.write_text(json.dumps(catalog, indent=2) + "\n")


def write_markdown(path: Path, models: list[dict], entries: list[dict], generated_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    free_sorted = sorted(models, key=lambda m: int(m.get("context_length") or 0), reverse=True)
    alias_by_upstream: dict[str, list[str]] = {}
    for e in entries:
        upstream = e["litellm_params"]["model"].removeprefix("openrouter/")
        alias_by_upstream.setdefault(upstream, []).append(e["model_name"])

    lines: list[str] = [
        "# OpenRouter free models (via AI-Gateway)",
        "",
        f"_Auto-generated {generated_at} by `scripts/sync_openrouter_free_models.py`. "
        "Do not edit the catalog table by hand — re-run the sync._",
        "",
        "Source: [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0)",
        "",
        "## How to call (always prefer LiteLLM)",
        "",
        "```bash",
        "export OPENAI_BASE_URL=http://localhost:4000/v1",
        'export OPENAI_API_KEY="$LITELLM_MASTER_KEY"',
        "# Curated:",
        "#   manager-openrouter-free / tier-free-cloud  → openrouter/free router",
        "#   manager-big-context / manager-understand-audit → defined in litellm_config.yaml, not here",
        "#   manager-audit-claude → poolside/laguna-xs-2.1:free",
        "# Direct free alias: or-free-<slug>",
        "```",
        "",
        "Agents (pi, OpenCode, tau) should use **gateway model ids**, not raw OpenRouter URLs,",
        "so Prometheus, retries, and fallbacks apply.",
        "",
        "## Catalog",
        "",
        f"**{len(models)}** free chat-candidate models → **{len(entries)}** LiteLLM aliases "
        "(includes curated names).",
        "",
        "| OpenRouter id | LiteLLM alias(es) | Ctx | Modality | Role |",
        "|---------------|-------------------|-----|----------|------|",
    ]

    for m in free_sorted:
        mid = m.get("id") or ""
        aliases = alias_by_upstream.get(mid) or [slugify(mid)]
        # Prefer curated first, then or-free
        aliases_s = ", ".join(f"`{a}`" for a in aliases)
        lines.append(
            f"| `{mid}` | {aliases_s} | {fmt_ctx(m.get('context_length'))} | "
            f"{modality_of(m)} | {role_for(mid)} |"
        )

    lines.extend(
        [
            "",
            "## Compare & contrast (use cases)",
            "",
            "| Job | Prefer | Why | Watch out |",
            "|-----|--------|-----|-----------|",
            "| Day-to-day **coding agent** | `poolside/laguna-m.1:free`, `laguna-xs-2.1:free`, "
            "`cohere/north-mini-code:free`, `qwen/qwen3-coder:free` | Built for agentic coding / tools | "
            "Free queueing; tool quality varies by provider |",
            "| **Huge codebase audit** / long logs | `qwen/qwen3-coder:free` (1M), "
            "`nvidia/nemotron-3-ultra*:free` / `super*:free` (1M) | Million-token context | "
            "Latency + free rate limits; still leaves host |",
            "| **Multimodal** free (image/video→text) | `google/gemma-4-*:free`, "
            "`nvidia/nemotron-*-vl*:free`, `nemotron-3-nano-omni*:free` | Free VLM path | "
            "**Never PHI**; prefer `manager-vision-local` / Gemini for controlled cloud |",
            "| Quick free fallback | `openrouter/free` → `manager-openrouter-free` / `tier-free-cloud` | "
            "Zero config router | **Random** free model — quality and tools are unpredictable |",
            "| General chat / summarization | Llama 3.3 70B, Hermes 405B, Qwen3-Next | Broad instruction following | "
            "Not specialized for coding agents |",
            "| Tiny / cheap experiments | Llama 3.2 3B, Nemotron Nano 9B, gpt-oss-20b | Low cost compute on provider side | "
            "Weak on hard coding / long agents |",
            "| Uncensored sandbox | Dolphin / Venice edition | Fewer refusals | **Avoid** for compliance, PHI, caregiving |",
            "",
            "### Vs local gateway tiers",
            "",
            "| | Local (`tier-local-fast` / turbo) | Gemini (`tier-gemini`) | Free OpenRouter | Paid Grok (`tier-paid-cloud`) |",
            "|--|-------------------------------|------------------------|-----------------|--------------------------------|",
            "| Privacy | Best (stays on host) | Leaves host (AI Studio) | Leaves host (OR + upstream) | Leaves host (xAI) |",
            "| Cost | Electricity only | Google One quota | $0 (rate-limited) | Paid |",
            "| Context | Model-bound (local VRAM) | Large | Up to **1M** free | Large |",
            "| Reliability | Your hardware | Good SLA-ish | Best-effort free tier | Paid SLA-ish |",
            "| Best for | PHI, default coding | Multimodal cloud, tools | Burst audits, overflow | Hard coding when free fails |",
            "",
            "## Limitations & other considerations",
            "",
            "1. **Privacy / PHI** — Free OpenRouter always leaves the Mac. Default M.A.N.A.G.E.R. path is "
            "`tier-local-fast` / `manager-fast-turbo`. Do not default free OR for caregiver data.",
            "2. **Churn** — Free list changes. Re-run `python3 scripts/sync_openrouter_free_models.py` "
            "(or the `openrouter-sync` compose profile). Stale `or-free-*` ids fail until re-sync.",
            "3. **Rate limits & queues** — Free endpoints throttle; expect 429s and long TTFT under load.",
            "4. **No SLA / tool-calling** — Agentic CLIs may break on models with weak tools; prefer "
            "Laguna / Qwen coder / North Mini for agents.",
            "5. **Router opacity** — `openrouter/free` does not guarantee a coding model; pin an id for audits.",
            "6. **Fallback graph** — Gateway already falls local → Gemini → free OR → Grok for many aliases; "
            "use tier names so that chain stays intact.",
            "7. **Modality mismatches** — VL models are not drop-in for pure text agent loops; use vision tiers.",
            "",
            "## Curated gateway aliases",
            "",
            "| Alias | Upstream |",
            "|-------|----------|",
        ]
    )
    for alias, mid in CURATED.items():
        lines.append(f"| `{alias}` | `{mid}` |")

    lines.extend(
        [
            "",
            "## Refresh",
            "",
            "```bash",
            "cd ~/ai-gateway",
            "set -a && source .env && set +a",
            "python3 scripts/sync_openrouter_free_models.py",
            "# if config_changed=true:",
            "./scripts/docker/compose.sh restart litellm",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--api-key", default=os.environ.get("OPENROUTER_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("OPENROUTER_API_KEY is required", file=sys.stderr)
        return 1

    try:
        all_models = fetch_models(args.api_key)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Failed to fetch OpenRouter models: {exc}", file=sys.stderr)
        return 1

    free_models = [m for m in all_models if is_free(m) and is_chat_candidate(m)]
    entries = build_entries(all_models)
    generated_at = datetime.now(timezone.utc).isoformat()

    yaml_text = render_yaml(entries, generated_at, len(free_models))
    previous = args.output.read_text() if args.output.exists() else ""
    args.output.write_text(yaml_text)
    write_catalog(args.catalog, free_models, entries, generated_at)
    write_markdown(args.markdown, free_models, entries, generated_at)

    # Compare only the model_list section — the header carries a fresh
    # generated_at timestamp every run, which made this always report
    # changed=true (and would restart litellm-proxy daily for no reason).
    def _model_list_only(text: str) -> str:
        idx = text.find("model_list:")
        return text[idx:] if idx != -1 else text

    changed = _model_list_only(yaml_text) != _model_list_only(previous)
    print(
        f"Synced {len(free_models)} free OpenRouter models -> {len(entries)} LiteLLM aliases"
    )
    print(f"YAML: {args.output}")
    print(f"Catalog: {args.catalog}")
    print(f"Markdown: {args.markdown}")
    if changed:
        print("config_changed=true")
    else:
        print("config_changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
