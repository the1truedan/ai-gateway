# PMB agent memory + model-staging practices

## PMB: shared context across cloud and local agents

[PMB](https://github.com/pmb-ai/pmb) is a local-first memory layer that any MCP-capable
agent (Claude Code, Codex, Grok CLI, or a local coding agent routed through this gateway)
can read from and write to. It's what lets a cloud agent hand a task to a local model —
or a different cloud agent — without re-deriving context from scratch.

### One workspace per project, not one global blob

PMB resolves which workspace (isolated memory store) an agent is using via, in priority
order: an explicit `PMB_WORKSPACE` env var, a project-local `.pmb/workspace.yaml` pin
file, a saved global default (`pmb workspace use`), then git-remote/cwd auto-detection.

**Lesson learned the hard way:** a saved global default silently outranks cwd-based
auto-detection everywhere it isn't overridden. Running `pmb` commands from a second
project's directory without either an explicit env var or a project pin will silently
read/write the *first* project's memory instead — no error, no warning. `pmb init` run
against an already-active workspace doesn't create a new one either; it can rename the
existing one in place if you pass `--name`.

**Fix:** pin every project explicitly with its own `.pmb/workspace.yaml` (created
automatically the first time `pmb init` resolves via git/cwd auto-detect, i.e. with no
global default already set — `pmb workspace use --clear` first if one is). Keep
`.pmb/` out of version control (it's local machine state, not portable across clones).

### Local embedding, not cloud

Point `embedding.backend` at `ollama` and `embedding.ollama_model` (not the unrelated
`embedding.model` key — a real gotcha) at a small local embedding model such as
`bge-m3`, hosted on whichever GPU-capable local host this gateway routes coding traffic
to. That keeps semantic recall entirely local — relevant for any workspace that might
ever touch sensitive content, and avoids per-query cloud embedding cost for what's
otherwise a cheap operation.

### Local LLM calls for maintenance, not cloud CLIs

PMB's own maintenance commands (module summarization, sleep-stage consolidation) default
to shelling out to whatever agent CLI is on `PATH` — which silently becomes real cloud
API spend for what's fundamentally a cheap, local-appropriate task. Point them at a local
Ollama backend instead. One real gotcha: hybrid-reasoning "thinking" models will burn an
entire small completion budget on their internal reasoning preamble and return an empty
response, which PMB then silently drops. Use a non-thinking model for these calls.

## Model staging: FluxDown, Hugging Face, Civitai

Lessons from staging LoRAs and checkpoints through a self-hosted download queue in front
of a shared model pool:

- **Container bind-mount paths, not host paths.** A download tool running in a container
  only sees its own container-internal path for the save directory — a host-style path
  that happens to also exist inside the container (because it was created there) will
  silently succeed and write into the container's own ephemeral layer instead of the
  bind-mounted host volume. The file looks completely fine until the container restarts
  and it's gone. Always use the container-side path from `docker inspect`'s bind mounts,
  never the host-side one, when staging into a containerized downloader.
- **Recovery when that happens anyway:** `docker cp` the stranded file out to the real
  host-mounted path, then run the normal promote step. No re-download needed.
- **Civitai auth:** append `?token=<key>` (or `&token=<key>` if the URL already has a
  query string — mixing up `?` vs `&` produces a silent 400, not an auth error, so it
  looks like a bad request rather than a formatting bug) to the download URL for
  version-gated files. A 401 on a URL that resolves fine in a browser usually means the
  file is real but auth-gated, not that the link is broken — verify against the
  provider's own API before assuming a link needs replacing.
- **Don't trust secondary-source model names.** Blog posts and search-result summaries
  about "new" local models are a common source of fabricated or renamed model IDs.
  Before staging anything, check the primary registry directly (the model host's own
  library page, or a direct `HEAD` request) — a 404 there means it doesn't exist under
  that name, regardless of how confidently a summary states otherwise.
- **Credentials belong in the existing gitignored `.env`,** in the same slot the deploy
  tooling already reads (`HF_TOKEN`, `CIVITAI_API_TOKEN`) — not a new file, not committed
  anywhere, not printed in logs.
