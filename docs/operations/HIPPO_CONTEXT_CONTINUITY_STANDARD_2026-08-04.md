# Hippo context-continuity standard (2026-08-04)

## Purpose

Prevent context loss when work moves between Grok/Tok wrappers, Claude/Codex,
Headroom/LiteLLM, and local MRGPU agents.

## Gateway contract

Headroom is the context-budget boundary. When `HIPPO_AUTO_CONTEXT=1`, the
caller may prepend a bounded, reference-only block from Hippo memories tagged
`agent-context` or `repeated-reminder`; Headroom then compresses the complete
request before forwarding it to LiteLLM. Direct provider CLIs are not assumed to
receive this context.

```text
Hippo recall (reviewed tags, bounded budget)
       ↓
Headroom :8787 (compression / redaction boundary)
       ↓
LiteLLM :4000 (routing / spend record)
       ↓
local MRGPU or approved cloud provider
```

## Session-end contract

Wrappers and native clients should run a detached Hippo session-end worker so
TUI teardown cannot interrupt consolidation. The worker extracts actionable
lessons, deduplicates, applies the secret veto, and makes only eligible
high-value memories available for later global promotion. Raw transcripts are
not a shared database.

## Cloud-to-local handoff

When cloud credits fail or a direct client loses context:

1. Capture the objective, changed files, tests, risks, and next command.
2. Start a new local Turnstone/pi/omp workstream through Headroom.
3. Give the local agent the handoff plus tagged Hippo recall, not an unbounded
   transcript dump.
4. Run an independent local review and write the result to `~/grokcode/docs`.

This preserves continuity while keeping provider boundaries and privacy
explicit. Hippo SQLite stores stay on local disks; do not place them on the
`ai-data` NFS share.

## Verification

```bash
curl -fsS http://127.0.0.1:8787/readyz
hippo status
hippo context --auto --budget 900
```

If a client bypasses Headroom, treat it as a separate, non-contextualized path
and record a handoff before switching agents.
