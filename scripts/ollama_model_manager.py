#!/usr/bin/env python3
"""Audit local Ollama models, compare registry manifests, and apply staged plans.

Does not download or remove anything unless you explicitly run `apply`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODELS_DIR = Path("/Volumes/models/ollama/models")
DEFAULT_PLAN_PATH = Path(__file__).resolve().parent / "ollama_staged_plan.json"
DEFAULT_GPU_HOST_PLAN_PATH = Path(__file__).resolve().parent / "ollama_staged_plan.gpu-host.json"
OLLAMA_API = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# M4 Mac Mini 24 GB unified memory — tuned to Grok share "Qwen3 vs Llama3.3" guidance:
# Llama 3.3 on Ollama is 70B-only (~43 GB) and is excluded. Qwen3/Qwen3.5 fit; Llama 3.1 8B
# is the viable Meta comparison point. Models >=16 GB are single-load only and often unusable
# with agent tooling + context. Second opinion: qwen3-coder:30b is quality-true / wrong host.
M4_24GB_PROFILE = {
    "hardware": "Apple M4 Mac Mini, 24 GB unified memory",
    "comfortable_max_gb": 12.0,
    "tight_max_gb": 15.0,
    "reject_above_gb": 16.0,
    "context_target": "64K-128K with tools/thinking enabled",
    "grok_share": "https://grok.com/share/c2hhcmQtNA_df5b772c-2fd6-473a-8dd2-548d90978af9",
    "fabric_share": "https://grok.com/share/c2hhcmQtNA_7cefc7c0-8c66-4dec-8a46-0b4ea9dd9cfb",
}

# gpu-host Pop!_OS sidecar — RTX 4060 Ti 16 GB + Ryzen 5 3600 + 62 GB RAM (<gpu-host-ip>).
# Multiple local model paths kept for now (service dir, ~/.ollama, /MCP_WIP/ollama);
# eventual merge to Unraid NFS v4.2 share mounted on boot from clients.
GPU_HOST_16GB_PROFILE = {
    "hardware": "gpu-host Pop!_OS, RTX 4060 Ti 16GB, Ryzen 5 3600, 62GB RAM",
    "host": "<gpu-host-ip>",
    "comfortable_max_gb": 12.0,
    "tight_max_gb": 15.0,
    "reject_above_gb": 16.0,
    "context_target": "32K-128K with tools; one large model at a time",
    "model_paths": [
        "/usr/share/ollama/.ollama/models",
        "$HOME/.ollama/models",
        "/MCP_WIP/ollama",
    ],
    "storage_note": (
        "Keep multi-path for now; later merge to Unraid NFS v4.2 share, "
        "client-mounted on boot (not manual mount)."
    ),
}

PROFILES = {
    "m4-24gb": M4_24GB_PROFILE,
    "gpu-host-16gb": GPU_HOST_16GB_PROFILE,
}

DEFAULT_LITELLM_CONFIGS = (
    Path(__file__).resolve().parent.parent / "litellm_config.yaml",
    Path(__file__).resolve().parent.parent / "litellm_config.linux.yaml",
)


@dataclass
class ModelAudit:
    name: str
    size_gb: float
    modified: str
    digest: str
    registry_status: str
    registry_note: str
    role: str = ""
    recommendation: str = ""
    reclaimable_gb: float = 0.0


@dataclass
class PlanAction:
    action: str  # pull | rm
    model: str
    reason: str
    size_gb: float = 0.0
    stage: int = 1
    enabled: bool = True
    role: str = ""
    litellm_route: str = ""


@dataclass
class StagedPlan:
    created_at: str
    models_dir: str
    actions: list[PlanAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "models_dir": self.models_dir,
            "notes": self.notes,
            "actions": [asdict(a) for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StagedPlan:
        actions = [PlanAction(**a) for a in data.get("actions", [])]
        return cls(
            created_at=data.get("created_at", ""),
            models_dir=data.get("models_dir", str(DEFAULT_MODELS_DIR)),
            actions=actions,
            notes=data.get("notes", []),
        )


def fetch_json(url: str) -> Any:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ollama-model-manager/1.0"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_remote_manifest(repo: str, tag: str) -> dict[str, Any]:
    url = f"https://registry.ollama.ai/v2/{repo}/manifests/{tag}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            "User-Agent": "ollama-model-manager/1.0",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode())


def parse_repo_tag(name: str) -> tuple[str | None, str | None]:
    if name.startswith("hf.co/"):
        return None, None
    if "/" in name:
        namespace, rest = name.split("/", 1)
        if ":" in rest:
            model, tag = rest.split(":", 1)
            return f"{namespace}/{model}", tag
        return f"{namespace}/{rest}", "latest"
    if ":" in name:
        model, tag = name.split(":", 1)
        return f"library/{model}", tag
    return f"library/{name}", "latest"


def manifest_fingerprint(manifest: dict[str, Any]) -> tuple[str, tuple[tuple[str, int], ...]]:
    cfg = manifest.get("config", {}).get("digest", "")
    layers = tuple(
        sorted((layer.get("digest", ""), layer.get("size", 0)) for layer in manifest.get("layers", []))
    )
    return cfg, layers


def read_local_manifest(models_dir: Path, repo: str, tag: str) -> dict[str, Any] | None:
    path = models_dir / "manifests" / "registry.ollama.ai" / repo / tag
    if not path.exists():
        return None
    return json.loads(path.read_text())


def local_models() -> list[dict[str, Any]]:
    return fetch_json(f"{OLLAMA_API}/api/tags")["models"]


def registry_check(models_dir: Path, name: str) -> tuple[str, str]:
    repo, tag = parse_repo_tag(name)
    if not repo or not tag:
        return "hf_import", "Third-party HuggingFace import; no Ollama registry manifest"

    local_manifest = read_local_manifest(models_dir, repo, tag)
    try:
        remote_manifest = fetch_remote_manifest(repo, tag)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return "unlisted", "Tag not found on registry (community or removed)"
        return "error", str(err)
    except Exception as err:  # noqa: BLE001
        return "error", str(err)

    if not local_manifest:
        return "missing_local_manifest", "Installed but local manifest file missing"

    if manifest_fingerprint(local_manifest) == manifest_fingerprint(remote_manifest):
        return "current", "Manifest matches registry.ollama.ai"

    return "outdated", "Registry manifest differs (template/layers updated)"


def classify(name: str, registry_status: str) -> tuple[str, str, float]:
    """Return role, recommendation, reclaimable_gb for removals."""
    size_map = {
        "qwen2.5-coder:14b": 9.0,
        "hf.co/tensorblock/Qwen2.5-Coder-32B-Instruct-bf16-GGUF:Q2_K": 12.3,
        "huihui_ai/jan-nano-abliterated:4b": 2.5,
        "gemma3:1b": 0.8,
        "nomic-embed-text:latest": 0.27,
        "mxbai-embed-large:latest": 0.67,
        "snowflake-arctic-embed:latest": 0.67,
        "embeddinggemma:latest": 0.62,
        "initium/law_model:latest": 4.1,
    }

    if name == "qwen2.5-coder:14b":
        return (
            "legacy coder (base)",
            "REMOVE — duplicate of instruct Q5_K_M; template also outdated on registry",
            size_map[name],
        )
    if name.startswith("hf.co/tensorblock/Qwen2.5-Coder-32B"):
        return (
            "legacy coder (HF Q2_K)",
            "REMOVE — Q2_K is very low quality; you already have better 14B instruct",
            size_map[name],
        )
    if name == "huihui_ai/jan-nano-abliterated:4b":
        return (
            "niche uncensored small",
            "REMOVE — 12mo old 4B; low utility vs gemma4:e4b",
            size_map[name],
        )
    if name == "gemma3:1b":
        return (
            "legacy small general",
            "REMOVE — superseded by gemma4:e2b/e4b",
            size_map[name],
        )
    if name == "nomic-embed-text:latest":
        return (
            "embedding v1",
            "REMOVE — superseded by nomic-embed-text-v2-moe (already installed)",
            size_map[name],
        )
    if name == "mxbai-embed-large:latest":
        return (
            "embedding (redundant)",
            "REMOVE — keep nomic-embed-text-v2-moe + bge-m3 only",
            size_map[name],
        )
    if name == "snowflake-arctic-embed:latest":
        return (
            "embedding (redundant)",
            "REMOVE — keep nomic-embed-text-v2-moe + bge-m3 only",
            size_map[name],
        )
    if name == "embeddinggemma:latest":
        return (
            "embedding (redundant)",
            "REMOVE on M4 stack — keep nomic-v2-moe + bge-m3 only",
            size_map[name],
        )
    if name == "initium/law_model:latest":
        return (
            "domain-specific legal",
            "KEEP unless unused — specialized 4.1GB legal model",
            0.0,
        )
    if name == "qwen2.5-coder:14b-instruct-q5_K_M":
        return (
            "primary coder (litellm/MCP tools)",
            "KEEP — M4-safe coder+tools; optional swap to qwen3.5:9b for lighter agent loop",
            0.0,
        )
    if name == "batiai/gemma4-26b:iq4":
        return (
            "primary orchestrator (litellm/MCP thinking+tools)",
            "KEEP — IQ4 quant fits 24 GB better than official gemma4:26b (~18 GB)",
            0.0,
        )
    if name == "nomic-embed-text-v2-moe:latest":
        return ("embedding (keep)", "KEEP — best nomic embed", 0.0)
    if name == "bge-m3:latest":
        return ("embedding (keep)", "KEEP — strong multilingual embed", 0.0)
    if registry_status == "outdated":
        return ("installed", f"UPDATE available — run staged pull for {name}", 0.0)
    return ("installed", "KEEP — current with registry", 0.0)


def audit(models_dir: Path) -> list[ModelAudit]:
    rows: list[ModelAudit] = []
    for model in sorted(local_models(), key=lambda m: m["name"]):
        name = model["name"]
        status, note = registry_check(models_dir, name)
        role, recommendation, reclaim = classify(name, status)
        rows.append(
            ModelAudit(
                name=name,
                size_gb=round(model["size"] / 1e9, 2),
                modified=model.get("modified_at", "")[:10],
                digest=model["digest"][:12],
                registry_status=status,
                registry_note=note,
                role=role,
                recommendation=recommendation,
                reclaimable_gb=reclaim,
            )
        )
    return rows


def _action(
    action: str,
    model: str,
    reason: str,
    *,
    size_gb: float = 0.0,
    stage: int = 1,
    enabled: bool = True,
    role: str = "",
    litellm_route: str = "",
) -> PlanAction:
    return PlanAction(
        action=action,
        model=model,
        reason=reason,
        size_gb=size_gb,
        stage=stage,
        enabled=enabled,
        role=role,
        litellm_route=litellm_route,
    )


def default_plan(audits: list[ModelAudit], models_dir: Path, profile: str = "m4-24gb") -> StagedPlan:
    if profile == "gpu-host-16gb":
        return default_plan_gpu_host(audits, models_dir)

    audit_by_name = {a.name: a for a in audits}
    installed = set(audit_by_name)

    def sz(model: str, fallback: float) -> float:
        return audit_by_name.get(model, ModelAudit(model, fallback, "", "", "", "", "")).size_gb or fallback

    plan = StagedPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        models_dir=str(models_dir),
        notes=[
            f"Profile: {M4_24GB_PROFILE['hardware']}",
            f"Grok models: {M4_24GB_PROFILE['grok_share']}",
            f"Grok fabric: {M4_24GB_PROFILE['fabric_share']}",
            "Second opinion: Qwen3/Qwen3.5 win on 24 GB; Llama 3.3 (Ollama 70B ~43 GB) does not fit.",
            "qwen3-coder:30b is quality pick / wrong host for M4 agent loops (stage 4).",
            "Stage 1: trim redundant embedders still on disk after prior cleanup.",
            "Stage 2: M4-safe specialist pulls (OCR + Greek translation) for MCP sub-agents.",
            "Stage 3: optional — qwen3.5:9b recommended; llama3.1:8b for Llama A/B only.",
            "Stage 4: rejected on 24 GB (enable only if you accept swap/thrashing).",
            "Runtime rule: one large model loaded at a time; embedders (~2 GB) can stay resident.",
            "Cloud: Gemini via GEMINI_API_KEY (not Ollama). Validate: scripts/check_litellm_routes.py",
            "OpenCV is not an Ollama model — use as MCP preprocess tool before OCR models.",
        ],
    )

    # Stage 1 — remaining cleanup on current disk
    stage1_removals = [
        (
            "embeddinggemma:latest",
            "Redundant third embedder; nomic-v2-moe + bge-m3 cover RAG",
            "embedding",
        ),
    ]
    for model, reason, role in stage1_removals:
        if model not in installed:
            continue
        plan.actions.append(
            _action(
                "rm",
                model,
                reason,
                size_gb=sz(model, 0.62),
                stage=1,
                enabled=True,
                role=role,
            )
        )

    # Stage 2 — specialist MCP sub-agents (M4-safe sizes)
    stage2_pulls = [
        (
            "glm-ocr:latest",
            2.22,
            "M4-safe OCR sub-agent (~2.2 GB); pair with OpenCV MCP preprocess",
            "ocr-subagent",
            "manager-ocr-local",
        ),
        (
            "translategemma:4b",
            3.30,
            "Greek (el/el-GR) + 55 langs; lighter than 12b for 24 GB model swapping",
            "translate-el-subagent",
            "manager-translate-el",
        ),
    ]
    for model, size, reason, role, route in stage2_pulls:
        if model in installed:
            continue
        plan.actions.append(
            _action(
                "pull",
                model,
                reason,
                size_gb=size,
                stage=2,
                enabled=True,
                role=role,
                litellm_route=route,
            )
        )

    # Stage 3 — optional agentic upgrades (disabled; pick one coder path)
    stage3_pulls = [
        (
            "qwen3.5:9b",
            6.59,
            "Grok/M4 pick: tools+thinking+128K at ~6.6 GB; best Qwen agent loop on 24 GB",
            "agent-upgrade-coder",
            "manager-fast-local",
            True,
        ),
        (
            "qwen3:8b",
            5.23,
            "Lighter Qwen3 agent alternative if qwen3.5 unavailable",
            "agent-upgrade-coder-alt",
            "manager-fast-local",
            False,
        ),
        (
            "llama3.1:8b",
            4.92,
            "Llama-side benchmark (Llama 3.3 70B won't fit); general chat sub-agent",
            "agent-llama-baseline",
            "manager-llama-local",
            False,
        ),
        (
            "gemma4:12b",
            7.56,
            "Vision+tools multimodal + reasoning; M4-safe size",
            "agent-vision-reason",
            "manager-vision-local",
            True,
        ),
        (
            "translategemma:12b",
            8.11,
            "Higher-quality Greek translation; only if 4b quality insufficient",
            "translate-el-premium",
            "manager-translate-el",
            False,
        ),
        (
            "deepseek-ocr:latest",
            6.69,
            "Higher-quality OCR; heavier than glm-ocr — use if layout accuracy matters",
            "ocr-premium",
            "manager-ocr-local",
            False,
        ),
    ]
    for model, size, reason, role, route, enabled in stage3_pulls:
        if model in installed:
            continue
        plan.actions.append(
            _action(
                "pull",
                model,
                reason,
                size_gb=size,
                stage=3,
                enabled=enabled,
                role=role,
                litellm_route=route,
            )
        )

    # Stage 4 — explicitly rejected for M4 24 GB
    stage4_rejected = [
        ("llama3.3:70b", 42.52, "Llama 3.3 on Ollama is 70B-only; impossible on 24 GB"),
        ("qwen3-coder:30b", 18.56, "quality pick / wrong host; MoE ~19 GB unusable with tools+context on Mini"),
        ("qwen3:30b-a3b", 18.56, "Same 24 GB constraint as qwen3-coder:30b"),
        ("gemma4:26b", 18.00, "Official 26B worse fit than batiai/gemma4-26b:iq4 already installed"),
        ("qwen3.5:27b", 17.42, "Too tight for reliable agent loops on 24 GB"),
        ("devstral-small-2:24b", 15.18, "M4 24 GB: technically loads, practically unusable with agents"),
    ]
    for model, size, reason in stage4_rejected:
        plan.actions.append(
            _action("pull", model, f"REJECTED M4-24GB — {reason}", size_gb=size, stage=4, enabled=False)
        )

    # Registry refresh for anything outdated that we are keeping
    removal_models = {a.model for a in plan.actions if a.action == "rm" and a.enabled}
    for a in audits:
        if a.registry_status != "outdated":
            continue
        plan.actions.append(
            _action(
                "pull",
                a.name,
                a.registry_note if a.name not in removal_models else f"Skipped — {a.registry_note}",
                size_gb=a.size_gb,
                stage=2,
                enabled=a.name not in removal_models,
            )
        )

    if profile not in PROFILES:
        plan.notes.insert(0, f"Warning: unknown profile '{profile}', using m4-24gb rules anyway.")

    return plan


def default_plan_gpu_host(audits: list[ModelAudit], models_dir: Path) -> StagedPlan:
    """Staged plan for gpu-host RTX 4060 Ti 16GB (litellm_config.linux.yaml)."""
    audit_by_name = {a.name: a for a in audits}
    installed = set(audit_by_name)
    prof = GPU_HOST_16GB_PROFILE

    def sz(model: str, fallback: float) -> float:
        return audit_by_name.get(model, ModelAudit(model, fallback, "", "", "", "", "")).size_gb or fallback

    plan = StagedPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        models_dir=str(models_dir),
        notes=[
            f"Profile: {prof['hardware']}",
            f"Host: {prof['host']}",
            f"Model paths (keep multi-path for now): {', '.join(prof['model_paths'])}",
            prof["storage_note"],
            "Comfortable ≤12 GB; tight single-load ≤15 GB; reject ≥16 GB for agent loops.",
            "Stage 1: repair/correctness pulls for linux LiteLLM routes.",
            "Stage 2: optional reclaim after gemma4 soak.",
            "Stage 3: optional single-load heavy (gpt-oss:20b).",
            "Stage 4: rejected — needs offload or NFS/shared heavy node.",
            "Runtime: one large model at a time; embedders can stay resident.",
            "Routes: litellm_config.linux.yaml (manager-reasoning-local=gemma4:12b, deepseek=14b).",
        ],
    )

    # Stage 1 — correctness pulls (enabled)
    stage1_pulls = [
        (
            "nomic-embed-text-v2-moe:latest",
            0.96,
            "Repair incomplete pull; manager-embed on linux overlay",
            "embedding",
            "manager-embed",
        ),
        (
            "translategemma:4b",
            3.30,
            "manager-translate-el Greek + multi-lang specialist",
            "translate-el",
            "manager-translate-el",
        ),
        (
            "deepseek-r1:14b",
            9.0,
            "Best DeepSeek for 4060 Ti 16GB; manager-reasoning-deepseek",
            "reasoning-deepseek",
            "manager-reasoning-deepseek",
        ),
    ]
    for model, size, reason, role, route in stage1_pulls:
        if model in installed:
            continue
        plan.actions.append(
            _action(
                "pull",
                model,
                reason,
                size_gb=size,
                stage=1,
                enabled=True,
                role=role,
                litellm_route=route,
            )
        )

    # Stage 2 — reclaim superseded + abliterated (enabled: no longer needed)
    stage2_rms = [
        ("gemma3:12b", "Superseded by gemma4:12b on manager-reasoning-local", "reasoning-legacy"),
        ("huihui_ai/jan-nano-abliterated:4b", "Abliterated models no longer needed; reclaim disk", "legacy-abliterated"),
    ]
    for model, reason, role in stage2_rms:
        if model not in installed:
            continue
        plan.actions.append(
            _action("rm", model, reason, size_gb=sz(model, 0.0), stage=2, enabled=True, role=role)
        )

    # Stage 3 — optional heavy single-load
    if "gpt-oss:20b" not in installed:
        plan.actions.append(
            _action(
                "pull",
                "gpt-oss:20b",
                "Optional heavy reasoner (~13.8 GB); exclusive single-load slot",
                size_gb=13.79,
                stage=3,
                enabled=False,
                role="heavy-reason",
                litellm_route="",
            )
        )

    # Stage 4 — rejected on 16 GB agent loops
    stage4_rejected = [
        ("deepseek-r1:32b", 19.85, "Needs heavy CPU offload; poor on 6c/12t"),
        ("deepseek-v3:latest", 404.0, "Full MoE impossible on 16 GB"),
        ("qwen3-coder:30b", 18.56, "Quality pick / wrong host for multi-model agent fabric"),
        ("qwen3:30b-a3b", 18.56, "Same 16 GB constraint"),
        ("gemma4:26b", 18.0, "Tight without IQ quant; use HF IQ only if quality chase"),
        ("qwen3.5:27b", 17.42, "Tight single-load; prefer 9b daily + 14b deepseek"),
        ("llama4:scout", 67.44, "Far beyond 16 GB VRAM"),
    ]
    for model, size, reason in stage4_rejected:
        plan.actions.append(
            _action(
                "pull",
                model,
                f"REJECTED gpu-host-16GB — {reason}",
                size_gb=size,
                stage=4,
                enabled=False,
            )
        )

    return plan


def print_audit_report(audits: list[ModelAudit], models_dir: Path) -> None:
    total = sum(a.size_gb for a in audits)
    reclaim = sum(a.reclaimable_gb for a in audits)
    print(f"Ollama model audit — {models_dir}")
    print(f"Total installed: {total:.1f} GB across {len(audits)} models")
    print(f"Recommended reclaim (stage 1): {reclaim:.1f} GB\n")

    print(f"{'MODEL':<55} {'GB':>5} {'REGISTRY':<10} RECOMMENDATION")
    print("-" * 120)
    for a in audits:
        print(f"{a.name:<55} {a.size_gb:5.1f} {a.registry_status:<10} {a.recommendation}")

    print("\nRegistry details:")
    for a in audits:
        print(f"  • {a.name}: {a.registry_note}")


def litellm_model_names(configs: tuple[Path, ...] = DEFAULT_LITELLM_CONFIGS) -> set[str]:
    names: set[str] = set()
    pattern = re.compile(r"^\s*-\s*model_name:\s*([^\s#]+)\s*$", re.M)
    for path in configs:
        if not path.exists():
            continue
        names.update(pattern.findall(path.read_text(encoding="utf-8")))
    return names


def warn_missing_litellm_routes(plan: StagedPlan) -> None:
    """Print WARN if enabled plan actions reference routes missing from litellm config."""
    names = litellm_model_names()
    if not names:
        print("\nWARN: no LiteLLM model_name entries found; skip route check")
        return
    missing = [
        a
        for a in plan.actions
        if a.enabled and a.litellm_route and a.litellm_route not in names
    ]
    if not missing:
        return
    print("\nWARN: litellm_route missing from litellm_config.yaml / .linux.yaml:")
    for a in missing:
        print(f"  • {a.model} -> {a.litellm_route}")
    print("  Fix config or run: python3 scripts/check_litellm_routes.py")


def print_plan_summary(plan: StagedPlan) -> None:
    print(f"\nStaged plan — {plan.created_at}")
    print(f"Models dir: {plan.models_dir}")
    for note in plan.notes:
        print(f"  - {note}")

    by_stage: dict[int, list[PlanAction]] = {}
    for action in plan.actions:
        by_stage.setdefault(action.stage, []).append(action)

    for stage in sorted(by_stage):
        enabled = [a for a in by_stage[stage] if a.enabled]
        disabled = [a for a in by_stage[stage] if not a.enabled]
        print(f"\nStage {stage} ({len(enabled)} enabled, {len(disabled)} disabled suggestions)")
        for action in by_stage[stage]:
            flag = "ON " if action.enabled else "off"
            size = f"{action.size_gb:.1f}GB" if action.size_gb else "n/a"
            role = f" [{action.role}]" if action.role else ""
            route = f" -> {action.litellm_route}" if action.litellm_route else ""
            print(
                f"  [{flag}] {action.action:4} {action.model:<42} {size:>7}{role}{route}  {action.reason}"
            )
    warn_missing_litellm_routes(plan)


def save_plan(plan: StagedPlan, path: Path) -> None:
    path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")
    print(f"\nWrote staged plan: {path}")


def apply_plan(plan: StagedPlan, dry_run: bool = True) -> None:
    enabled = [a for a in plan.actions if a.enabled]
    if not enabled:
        print("No enabled actions in plan.")
        return

    print(f"{'DRY RUN — no changes' if dry_run else 'APPLYING PLAN'} ({len(enabled)} actions)")
    for action in enabled:
        cmd = ["ollama", action.action, action.model]
        print(f"  $ {' '.join(cmd)}  # {action.reason}")
        if not dry_run:
            subprocess.run(cmd, check=True)

    if dry_run:
        print("\nRe-run with: apply --execute")


def cmd_audit(args: argparse.Namespace) -> int:
    models_dir = Path(args.models_dir)
    audits = audit(models_dir)
    print_audit_report(audits, models_dir)
    if args.write_plan:
        plan = default_plan(audits, models_dir, profile=args.profile)
        save_plan(plan, Path(args.plan))
        print_plan_summary(plan)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    models_dir = Path(args.models_dir)
    audits = audit(models_dir)
    plan = default_plan(audits, models_dir, profile=args.profile)
    save_plan(plan, Path(args.plan))
    print_plan_summary(plan)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.plan)
    if not path.exists():
        print(f"Plan not found: {path}", file=sys.stderr)
        return 1
    plan = StagedPlan.from_dict(json.loads(path.read_text()))
    print_plan_summary(plan)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    path = Path(args.plan)
    if not path.exists():
        print(f"Plan not found: {path}", file=sys.stderr)
        return 1
    plan = StagedPlan.from_dict(json.loads(path.read_text()))
    apply_plan(plan, dry_run=not args.execute)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", default=str(DEFAULT_MODELS_DIR))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    profile_kwargs = {
        "default": "m4-24gb",
        "choices": sorted(PROFILES.keys()),
        "help": "Hardware profile used to tune staged pulls/rejections (m4-24gb | gpu-host-16gb)",
    }

    audit_parser = sub.add_parser("audit", help="Audit local models vs registry")
    audit_parser.add_argument("--write-plan", action="store_true", help="Also write default staged plan JSON")
    audit_parser.add_argument("--profile", **profile_kwargs)
    audit_parser.set_defaults(func=cmd_audit)

    plan_parser = sub.add_parser("plan", help="Generate default staged plan JSON")
    plan_parser.add_argument("--profile", **profile_kwargs)
    plan_parser.set_defaults(func=cmd_plan)

    show_parser = sub.add_parser("show", help="Show an existing staged plan")
    show_parser.set_defaults(func=cmd_show)

    apply_parser = sub.add_parser("apply", help="Apply enabled actions from staged plan")
    apply_parser.add_argument("--execute", action="store_true", help="Actually run ollama pull/rm")
    apply_parser.set_defaults(func=cmd_apply)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())