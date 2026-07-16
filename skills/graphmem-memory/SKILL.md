---
name: graphmem-memory
description: Use the graphmem knowledge-graph memory well. Trigger whenever the user asks to remember/recall something, asks "what do you know about X", mentions their memory/knowledge graph, asks where something is deployed, needs a stored credential/env var, or when durable cross-session knowledge should be saved. Also trigger before answering questions about the user's servers, projects, or infrastructure — check the graph first.
---

# graphmem — how to use the memory well

graphmem MCP tools: `remember` · `recall` · `search` · `get` · `link` · `walk` ·
`update` · `forget` · `vocab` · `stats` · `export`. Backend: a shared cloud DB
(Oracle ADB) — every device sees the same graph.

## Reading (do this before answering questions about the user's world)
- **Always query `recall` in ENGLISH.** The embedding model is English-centric; a
  Turkish/other-language query retrieves poorly even for content on the same topic.
  If the user asks in another language, translate the intent to English for the query.
  For an exact non-English term, use `search` (keyword, language-agnostic) instead.
- **Semantic**: `recall(query)` — returns top hits + their 1-hop neighborhood. Best first move.
- **Exact/filtered**: `search(text, domain, kind)` — e.g. `search(kind='credential')` lists stored secrets.
- **Deep dive**: `get(name)` for the full body; follow `edges` by calling `get` on neighbors, or `walk(name, depth)` for the weighted neighborhood.
- Deployment questions ("where does X run?"): `get` the device nodes (kind=device) or walk from them.
- Credentials/env vars: stored as kind=credential nodes, values in `attrs` (see node `secrets-convention`). `get(name)` returns them.

## Writing (librarian discipline — the graph must compound, not rot)
1. **Before creating, check**: `recall` the topic. If a node exists → `update` it (or `link` to it), don't duplicate.
2. `remember` is dedup-first: if it returns `not_saved` with duplicates, DEFAULT to updating/linking the existing node; only `force=true` when it's genuinely a distinct topic.
3. **Bodies are self-contained mini-READMEs**: verbatim commands, exact values, CAPS section labels (WHAT/HOW/RUN/GOTCHA). Never "see file X" — the graph is read from other devices.
4. `summary` (1-3 sentences) drives semantic search — write it for retrieval. Machine-readables go in `attrs`.
5. **Always link**: accept sensible `link_suggestions`; everything on a machine links `deployed_on`/`part_of` its device node (kind=device). No orphans.
6. Vocabulary is open but registered: `vocab()` lists domains/kinds/rels; add via `vocab(action='add')` only for genuinely new categories.
7. Facts rot: when you verify something still true, `update(name, verified=true)`; when superseded, link `supersedes` and archive the old one (`forget`, soft).

## Conventions live in the graph itself
Read nodes `graphmem-usage-guide`, `device-registry`, `secrets-convention`,
`prompt-onboard-new-device` when in doubt — they are the source of truth.
