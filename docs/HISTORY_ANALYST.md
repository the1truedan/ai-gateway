# History Analyst: ask Open WebUI about every past agent session

One chat preset in Open WebUI that can answer questions like *"which sessions discussed X
last week?"* or *"which planned items were talked about but never tested?"* across Claude Code,
Codex, Grok, ChatGPT and shell history, and cite the session IDs it used.

Other memory tools each see one agent or one project. This one sees the whole history at once,
because it sits on a single session archive that every agent's logs already feed.

## How it fits together

```
Open WebUI  ── preset "History Analyst" ──►  Headroom  ──►  LiteLLM  ──►  local model (Ollama)
   │   tools: AgentsView MCP (sessions), Hister MCP (browser/shell history)
   │   knowledge: small markdown digests (session audits, planned-vs-tested lists)
   └── embeddings: bge-m3 on Ollama + hybrid (BM25 + vector) search
```

| Piece | Role | Upstream |
|---|---|---|
| AgentsView | Indexes local agent session logs into Postgres; `agentsview mcp` serves them read-only | https://github.com/kenn-io/agentsview |
| Open WebUI | Chat UI, MCP tool servers, Knowledge collections, model presets | https://github.com/open-webui/open-webui |
| Hister | Browser/shell history search, exposed as a second MCP tool | https://github.com/asciimoo/hister |
| Headroom | OpenAI-compatible proxy in front of LiteLLM (token accounting, caching) | https://github.com/chopratejas/headroom |
| LiteLLM | Routes the preset's model name to a local worker | https://github.com/BerriAI/litellm |
| Ollama | Runs the answering model and the embedding model | https://github.com/ollama/ollama |
| bge-m3 | Embedding model (8k-token window, strong on long text) | https://huggingface.co/BAAI/bge-m3 |

## Setup

1. **AgentsView MCP.** Run the `agentsview-mcp` service in `deploy/agentsview/docker-compose.yml`
   (same image and database as AgentsView, StreamableHTTP on `:42101`). Binding to a non-loopback
   address makes AgentsView require `Authorization: Bearer <auth_token>`.
2. **Tool servers in Open WebUI.** Admin > Settings > Tools: add the AgentsView MCP URL with the
   bearer token, and Hister's MCP URL if you run it.
3. **Preset.** Workspace > Models > new model `history-analyst`, base model = your local reasoning
   route, tools = both MCP servers. System prompt used here:

   > You are the History Analyst for this agent fleet. Answer questions about past
   > Grok/Claude/Codex/ChatGPT sessions and shell history using the AgentsView and Hister tools.
   > Use list_sessions(agent, date_from, date_to) for agent/date filters and search_sessions(query)
   > for keywords. Always cite session_id values. Never dump whole transcripts: use
   > get_session_overview first, then get_messages with small limits. Say plainly when a tool
   > returns nothing.

4. **Knowledge digests.** Generate small markdown digests (IDs, titles, counts, no transcript
   bodies) and push them with `scripts/history/owui_knowledge.py`:

   ```python
   from pathlib import Path
   from owui_knowledge import OwuiKnowledge
   owui = OwuiKnowledge()                       # OWUI_URL + OWUI_API_KEY
   res = owui.push("Session audits", "Weekly session audits", Path("audit.md"))
   owui.attach("history-analyst", res["knowledge_id"], "Session audits", full_context=True)
   ```

5. **Embeddings.** Admin > Settings > Documents: engine Ollama, model `bge-m3`, hybrid search on.
   Then re-index existing collections (`POST /api/v1/knowledge/reindex`).

## Gotchas we hit (Open WebUI 0.10.2)

- **API calls don't apply a preset's knowledge by themselves.** `POST /api/chat/completions`
  with an API key needs `files: [{"type": "collection", "id": "<knowledge id>"}]` in the body.
  The browser UI applies it automatically.
- **"List all X" needs full context.** Default retrieval returns the top few chunks, so a
  question over a 74-row digest named 2 rows. Set `"context": "full"` on the knowledge entry
  (`attach(..., full_context=True)`) or on the `files` item. Table digests also chunk badly:
  keep them on full context and use hybrid chunk search for prose.
- **Context window is the real limit.** At `num_ctx: 32768` the answer ran out of room at 70 of 74
  rows. Raising the worker to `num_ctx: 131072` (qwen3.5:9b, 10.2 GB, fits a 16 GB card) gave a
  complete, self-terminating answer with every cited session ID real. Split that worker from any
  shared YAML anchor so other routes keep their own context size.
- **Ollama URL from inside the container.** Use the compose service name
  (`http://ollama:11434`). `host.docker.internal` did not resolve in this setup.
- **Headroom caches identical prompts.** When A/B testing a model change, reword the question or
  you get the previous answer back in 0.1 s. Headroom doesn't compress user/system messages by
  default, which is what you want for ID lists.

## Privacy

Everything above runs on your own machines. Keep sensitive material on a local-only worker:
point the preset (or your router's sensitive-data rule) at a route that never falls back to a
cloud provider, and check that Open WebUI's embedding engine is local, not the OpenAI default.
Digests pushed to Knowledge should carry IDs and titles, not transcript text.
