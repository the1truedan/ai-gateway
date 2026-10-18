# Hippo first-prompt placement

This is the canonical placement for approved Hippo context in the gateway:

```text
client request
  → collect user messages
  → Hippo recall (explicitly tagged reminders only, bounded budget)
  → Prompt-I/O scan / privacy gate
  → Headroom compression
  → LiteLLM routing
  → local or explicitly approved provider
```

Hippo recall belongs immediately before Headroom because the recalled block is
part of the prompt budget and must be compressed, redacted, and routed under the
same policy as the user request. It must not be injected after compression or
inside LiteLLM provider adapters.

The recall block is reference-only and never a new instruction. Eligibility is
limited to `agent-context` and `repeated-reminder`; raw transcripts, PHI,
secrets, and unreviewed clipboard text are excluded. A failed Hippo lookup is
non-fatal and leaves the original request unchanged.

Native Codex/Claude/OpenCode clients may use Hippo MCP directly. Grok-tua and
Tok-tua wrappers use the same gateway seam when they route through Headroom.
Direct provider CLIs that bypass Headroom do not receive automatic Hippo context;
they must perform explicit MCP recall or record a handoff.

This placement gives every CLI agent a common, auditable gateway contract while
preserving local-only memory storage and the existing prompt-I/O privacy
boundary.
