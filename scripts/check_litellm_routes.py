#!/usr/bin/env python3
"""Check that litellm_route values in staged plans exist as model_name in LiteLLM config.

No network. Exit 1 if any enabled plan action references a missing route.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIGS = [
    ROOT / "litellm_config.yaml",
    ROOT / "litellm_config.linux.yaml",
]
DEFAULT_PLANS = [
    ROOT / "scripts" / "ollama_staged_plan.json",
    ROOT / "scripts" / "turboquant_staged_plan.json",
]

MODEL_NAME_RE = re.compile(r"^\s*-\s*model_name:\s*([^\s#]+)\s*$", re.M)
REQUIRED_ROLES = {
    "role-plan",
    "role-recon",
    "role-execute",
    "role-reason",
    "role-phi-local",
    "role-audit",
    "tier-gemini-free",
    "tier-codex-cloud",
    "tier-mimo-cloud",
}
LOCAL_ONLY_FALLBACKS = {
    "manager-fast-local",
    "manager-reasoning-local",
    "manager-phi-reason-local",
}
PAID_FALLBACKS = {
    "manager-codex-cloud",
    "tier-codex-cloud",
    "manager-mimo-cloud",
    "tier-mimo-cloud",
    "manager-grok-coding",
    "tier-paid-cloud",
}
AUTO_LOCAL_ROLES = {
    "role-plan",
    "role-recon",
    "role-execute",
    "role-reason",
    "role-phi-local",
    "role-audit",
    "tier-local-fast",
    "tier-local-reason",
    "tier-local-vision",
}
CLOUD_NAME_PARTS = ("gemini", "openrouter", "grok", "codex", "mimo", "cloud", "claude")


def model_names_from_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return set(MODEL_NAME_RE.findall(text))


def fallback_targets(text: str, model_name: str) -> set[str] | None:
    match = re.search(
        rf"^\s*-\s*{re.escape(model_name)}:\s*\[([^\]]*)\]\s*$", text, re.M
    )
    if not match:
        return None
    return {item.strip() for item in match.group(1).split(",") if item.strip()}


def routes_from_plan(path: Path, *, enabled_only: bool) -> list[tuple[str, str, bool]]:
    """Return list of (plan_path, route, enabled)."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, str, bool]] = []
    for action in data.get("actions", []):
        route = (action.get("litellm_route") or "").strip()
        if not route:
            continue
        enabled = bool(action.get("enabled", True))
        if enabled_only and not enabled:
            continue
        out.append((path.name, route, enabled))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-actions",
        action="store_true",
        help="Also require routes for disabled plan actions",
    )
    parser.add_argument(
        "--config",
        action="append",
        type=Path,
        help="LiteLLM YAML (repeatable). Default: mac + linux configs",
    )
    parser.add_argument(
        "--plan",
        action="append",
        type=Path,
        help="Staged plan JSON (repeatable)",
    )
    args = parser.parse_args()

    configs = args.config or DEFAULT_CONFIGS
    plans = args.plan or DEFAULT_PLANS
    enabled_only = not args.all_actions

    names: set[str] = set()
    config_errors: list[str] = []
    for cfg in configs:
        found = model_names_from_yaml(cfg)
        names |= found
        print(f"{cfg.name}: {len(found)} model_name entries")
        missing_roles = REQUIRED_ROLES - found
        if missing_roles:
            config_errors.append(
                f"  {cfg.name}: missing required role aliases: "
                + ", ".join(sorted(missing_roles))
            )

        text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        phi_fallbacks = fallback_targets(text, "role-phi-local")
        if phi_fallbacks is None:
            config_errors.append(f"  {cfg.name}: role-phi-local has no explicit fallback chain")
        elif not phi_fallbacks <= LOCAL_ONLY_FALLBACKS:
            config_errors.append(
                f"  {cfg.name}: role-phi-local fallbacks must be non-empty and local-only; "
                f"found {sorted(phi_fallbacks)}"
            )

        for phi_target in phi_fallbacks or ():
            target_fallbacks = fallback_targets(text, phi_target)
            if target_fallbacks is None:
                config_errors.append(
                    f"  {cfg.name}: PHI fallback target {phi_target} needs an explicit "
                    "terminal/local-only fallback chain"
                )
            elif not target_fallbacks <= LOCAL_ONLY_FALLBACKS:
                config_errors.append(
                    f"  {cfg.name}: PHI fallback target {phi_target} reaches non-local "
                    f"targets {sorted(target_fallbacks - LOCAL_ONLY_FALLBACKS)}"
                )

        for local_role in AUTO_LOCAL_ROLES:
            targets = fallback_targets(text, local_role) or set()
            leaked = {
                target
                for target in targets
                if target in PAID_FALLBACKS
                or any(part in target.lower() for part in CLOUD_NAME_PARTS)
            }
            if leaked:
                config_errors.append(
                    f"  {cfg.name}: {local_role} silently reaches cloud targets "
                    f"{sorted(leaked)}; cloud aliases must be selected explicitly"
                )

        if cfg.name.endswith(".linux.yaml"):
            for env_base in (
                "os.environ/OLLAMA_API_BASE",
                "os.environ/TURBOQUANT_CODER_API_BASE",
                "os.environ/TURBOQUANT_ORCH_API_BASE",
            ):
                if env_base not in text:
                    config_errors.append(f"  {cfg.name}: missing Linux API base {env_base}")

    if not names:
        print("ERROR: no model_name entries found in configs", file=sys.stderr)
        return 1

    if config_errors:
        print("CONFIG errors:")
        for line in config_errors:
            print(line)
        return 1

    missing: list[str] = []
    checked = 0
    for plan in plans:
        for plan_name, route, enabled in routes_from_plan(plan, enabled_only=enabled_only):
            checked += 1
            if route not in names:
                flag = "enabled" if enabled else "disabled"
                missing.append(f"  [{flag}] {plan_name}: litellm_route={route!r} not in config")

    print(f"Checked {checked} plan route reference(s); union of {len(names)} model names")
    if missing:
        print("MISSING routes:")
        for line in missing:
            print(line)
        return 1

    print("OK — all plan litellm_route values exist in LiteLLM config")
    return 0


if __name__ == "__main__":
    sys.exit(main())
