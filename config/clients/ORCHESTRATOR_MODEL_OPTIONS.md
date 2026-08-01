# 🧭 Mac Orchestrator model options and NVIDIA test guide

This guide tests the production path from a terminal on the M4 Mac:

```text
Pi / OMP / OpenCode
  → Mac Headroom http://localhost:8787/v1
  → Mac Orchestrator http://orchestrator:8790/v1
  → Mac LiteLLM central bus
  → gpu-host raw LiteLLM http://<gpu-host-ip>:4000/v1
  → NVIDIA Ollama http://<gpu-host-ip>:11434
```

Use `:8787` for these tests. Calling Mac `:4000`, gpu-host `:4000`, or Ollama
`:11434` directly bypasses part or all of the orchestration path.

## 🎛️ Agent-facing model options

| Model | Emoji | What the orchestrator does | Cloud policy |
|---|---:|---|---|
| `role-auto` | 🧭 | Classifies the prompt and chooses mac-client, gpu-host, or NAS-HOST from task fit and live capacity | Never selects cloud automatically |
| `role-plan` | 🗺️ | Local planning/reasoning role on the best suitable local host | Local only |
| `role-recon` | 🔎 | Explicit recon role; currently treated as an explicit free-cloud choice | Free cloud, explicit only |
| `role-execute` | 🛠️ | Local coding/tool-execution role; NVIDIA/CUDA wording prefers gpu-host | Local only |
| `role-reason` | 🧠 | Local reasoning role; NVIDIA/CUDA wording prefers gpu-host | Local only |
| `role-phi-local` | 🏥🔒 | Detects or explicitly marks PHI and confines it to an eligible local host | Cloud forbidden |
| `role-audit` | 🧪 | Local second-opinion/audit role | Local only |
| `tier-local-fast` | ⚡ | Explicit local fast compatibility alias | Local only |
| `tier-local-reason` | 🤔 | Explicit local reasoning compatibility alias | Local only |
| `tier-local-vision` | 👁️ | Vision work; image/OpenCV/OCR wording prefers NAS-HOST | Local only |
| `nas-host-small-fast` | 🗄️⚡ | Requests NAS-HOST's small fast worker | Local only |
| `nas-host-vision-local` | 🗄️👁️ | Requests NAS-HOST's local vision worker | Local only |
| `tier-nvidia-fast` | 🟩⚡ | Hard-selects gpu-host's NVIDIA execution route | Local only |
| `tier-nvidia-reason` | 🟩🧠 | Hard-selects gpu-host's NVIDIA reasoning route | Local only |
| `tier-free-cloud` | ☁️🆓 | Explicit OpenRouter free selection | Explicit only; never PHI |
| `manager-openrouter-free` | 🌐🆓 | Explicit OpenRouter free-router alias | Explicit only; never PHI |
| `tier-gemini-free` | ✨🆓 | Explicit Gemini free-project selection | Explicit only; never PHI |
| `tier-codex-cloud` | ☁️💻 | Explicit paid Codex/OpenAI selection | Explicit approval; never PHI |
| `tier-mimo-cloud` | ☁️🧩 | Explicit paid MiMo selection | Explicit approval; never PHI |
| `tier-grok-cloud` | ☁️🚀 | Explicit paid Grok selection | Explicit approval; never PHI |

## 🟩 gpu-host Ollama mappings

When gpu-host is selected, Mac LiteLLM translates the public role to an internal
`gpu-host-*` alias and calls the authenticated worker endpoint on
`<gpu-host-ip>:4000`.

| Public role | Internal Mac alias | NVIDIA Ollama model on gpu-host |
|---|---|---|
| `role-execute` | `gpu-host-role-execute` | `qwen3.5:9b` |
| `role-reason` | `gpu-host-role-reason` | `deepseek-r1:14b` |
| `role-plan` | `gpu-host-role-plan` | `deepseek-r1:14b` |
| `role-recon` | `gpu-host-role-recon` | `deepseek-r1:14b` when used as a local worker alias |
| `role-audit` | `gpu-host-role-audit` | `deepseek-r1:14b` |
| `role-phi-local` | `gpu-host-role-phi-local` | `qwen3.5:9b` |
| `tier-nvidia-fast` | worker-local alias | `qwen3.5:9b` (native tool calls) |
| `tier-nvidia-reason` | worker-local alias | `deepseek-r1:14b` |

The `gpu-host-*` names are internal bus aliases, not normal agent-facing model
choices.

## 🧪 Prepare a Mac terminal

Run this once in each terminal before launching a client. `AI_GATEWAY_ROOT`
stays fixed even when the repository being inspected is somewhere else:

```bash
export AI_GATEWAY_ROOT=$HOME/ai-gateway
set -a
source "$AI_GATEWAY_ROOT/.env"
set +a

export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_BASE="$OPENAI_BASE_URL"
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
export LITELLM_BASE_URL="$OPENAI_BASE_URL"
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"

test -n "$LITELLM_MASTER_KEY" || {
  echo "LITELLM_MASTER_KEY is missing"
  false
}
```

Confirm that Headroom is connected to the Mac orchestrator:

```bash
curl -fsS http://localhost:8787/readyz |
  jq '.checks.upstream'
```

Expected upstream URL: `http://orchestrator:8790`.

## 🎯 Make the semantic router prefer gpu-host

Host placement is semantic and capacity-aware. A model name alone is not a
hard host pin. Start the session with explicit NVIDIA context, for example:

> NVIDIA CUDA orchestration test: work on this implementation using the RTX
> worker. First report which backend the gateway selected, then inspect this
> repository and help me implement or test the requested change.

For semantic placement, select `role-auto` or `role-execute`. The words
`NVIDIA` and `CUDA` cause the local-host preference order to start with gpu-host.
For a deterministic worker test, select `tier-nvidia-fast` or
`tier-nvidia-reason`; these aliases hard-select gpu-host and fail closed if it is
saturated or unavailable. Neither path silently moves the request to cloud.

Dry-run the decision without making an LLM call:

```bash
curl -fsS http://localhost:8790/v1/router/decision \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "role-auto",
    "messages": [{
      "role": "user",
      "content": "Implement and benchmark this CUDA kernel on the NVIDIA GPU"
    }]
  }' | jq
```

Expected fields include:

```json
{
  "selected_host": "gpu-host",
  "selected_model": "role-execute",
  "tier": "local"
}
```

## 🥧 Launch Pi

Qwen 3.5 9B is reliable with a compact coding tool schema. On mac-client, the zsh
`pi` wrapper launches with `--no-extensions --tools read,bash,grep` to prevent
small-model tool-schema overload; `pi-full` preserves the original extension-
heavy launch for a larger backend.

The repository provider snippet is
`config/clients/pi.gpu-host.models.json`. Merge its `gpu-host-headroom` provider into
`~/.pi/agent/models.json` if it is not already present; do not discard other
providers in that file.

Then launch an interactive session:

```bash
pi --model gpu-host-headroom/role-auto \
  "NVIDIA CUDA orchestration test: use the RTX worker and inspect this repo."
```

To request the execution role explicitly while retaining semantic placement:

```bash
pi --model gpu-host-headroom/role-execute \
  "NVIDIA CUDA test: help me implement and benchmark a small kernel."
```

For a hard gpu-host pin, use `gpu-host-headroom/tier-nvidia-fast` instead.

## 🐙 Launch OMP

OMP can use the repository overlay without changing the normal user config:

```bash
omp --config "$AI_GATEWAY_ROOT/config/clients/omp.gpu-host.models.yml" \
  "NVIDIA CUDA orchestration test: use the RTX worker and inspect this repo."
```

The overlay defaults to the hard-pinned `tier-nvidia-fast` route. OMP 17
resolves `--model` before loading `--config`, so do not combine those flags for
a provider that exists only in the overlay. To choose other gpu-host roles with
`--model`, merge the overlay provider into `~/.omp/agent/models.yml` first.
For normal launches, also set `modelRoles.default` in
`~/.omp/agent/config.yml` to `gpu-host-headroom/tier-nvidia-fast`; the provider
catalog and the persisted default role live in separate OMP files.

After merging it into the user config, semantic execution can be selected with:

```bash
omp --model gpu-host-headroom/role-execute \
  "NVIDIA CUDA test: help me implement and benchmark a small kernel."
```

Model registration check:

```bash
omp --config "$AI_GATEWAY_ROOT/config/clients/omp.gpu-host.models.yml" models
```

## 🟦 Launch OpenCode

Use the checked-in test configuration for an isolated launch:

```bash
OPENCODE_CONFIG="$AI_GATEWAY_ROOT/config/clients/opencode.gpu-host.json" \
  opencode --model gpu-host-headroom/role-auto \
  "NVIDIA CUDA orchestration test: use the RTX worker and inspect this repo."
```

Or select execution explicitly:

```bash
OPENCODE_CONFIG="$AI_GATEWAY_ROOT/config/clients/opencode.gpu-host.json" \
  opencode --model gpu-host-headroom/role-execute \
  "NVIDIA CUDA test: help me implement and benchmark a small kernel."
```

For a hard gpu-host pin, use `gpu-host-headroom/tier-nvidia-fast` instead.

If the installed OpenCode build does not honor `OPENCODE_CONFIG`, merge the
`gpu-host-headroom` provider from the checked-in file into
`~/.config/opencode/opencode.json` and use the same `--model` value.

## ✅ Verify the request really used NVIDIA Ollama

For a compact request that exposes response headers:

```bash
curl -sS -D /tmp/gpu-host-orchestration.headers \
  http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "role-auto",
    "messages": [{
      "role": "user",
      "content": "Implement a tiny CUDA kernel on NVIDIA"
    }],
    "max_tokens": 32
  }' | jq

rg -i '^(x-manager-|x-litellm-call-id|x-litellm-model-api-base|x-headroom-)' \
  /tmp/gpu-host-orchestration.headers
```

Look for all of the following:

- 🟩 `x-manager-selected-host: gpu-host`
- 🛠️ `x-manager-selected-model: role-execute`
- 🧾 `x-litellm-call-id: ...`
- 🌐 `x-litellm-model-api-base: http://<gpu-host-ip>:4000/v1`
- ✂️ `x-headroom-tokens-before`, `x-headroom-tokens-after`, and
  `x-headroom-tokens-saved`

Optionally watch the RTX while the request is running:

```bash
ssh youruser@<gpu-host-ip> watch -n 1 nvidia-smi
```

## 🚧 Direct pinning versus orchestration testing

| Goal | Endpoint/model | What it tests |
|---|---|---|
| Test the complete manager path | Mac `:8787`, `role-auto`, NVIDIA/CUDA prompt | Headroom + orchestrator + central ledger + gpu-host worker |
| Test an explicit role with orchestration | Mac `:8787`, `role-execute`, NVIDIA/CUDA prompt | Same path with classification bypassed but host placement retained |
| Hard-pin the gpu-host bus alias | Mac `:4000`, `gpu-host-role-execute` | Central LiteLLM and gpu-host only; bypasses Headroom and orchestrator |
| Test gpu-host LiteLLM directly | gpu-host `:4000`, `role-execute` | Worker LiteLLM/Ollama only |
| Test Ollama directly | gpu-host `:11434` | Ollama and GPU only |

For orchestration testing, use one of the first two rows.

## 🔐 Safety reminders

- Automatic routing is local-only.
- Cloud aliases are consent signals and must be selected explicitly.
- Never use a cloud alias for PHI, caregiver, or medical-record content.
- `role-phi-local` cannot route to cloud.
- A manager outage fails closed; nas-host does not take over automatically.

## 🧯 Client troubleshooting

### OMP says `Config overlay not found`

Do not build the overlay path from `$PWD`; `$PWD` is the repository OMP is
inspecting. Export the gateway root first and let the overlay choose its
default NVIDIA model:

```bash
export AI_GATEWAY_ROOT=$HOME/ai-gateway
set -a
source "$AI_GATEWAY_ROOT/.env"
set +a

omp --config "$AI_GATEWAY_ROOT/config/clients/omp.gpu-host.models.yml" \
  "Inspect this repository and help me test the NVIDIA worker."
```

OMP 17 resolves `--model` before a one-run `--config` overlay is loaded. The
overlay therefore carries `model: gpu-host-headroom/tier-nvidia-fast`; omit
`--model` unless the provider has been merged into the persistent OMP config.

### Pi prints `Failed to register provider: Claude Code CLI not found`

That message comes from the optional `pi-claude-cli` extension, not the
AI-Gateway provider. Pi can continue and complete the NVIDIA request after the
warning. Either install/authenticate Claude Code if that extension is wanted,
or disable/remove the extension from the Pi extension configuration. It is not
required for `gpu-host-headroom/tier-nvidia-fast`.
