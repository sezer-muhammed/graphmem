# GraphMem — Knowledge-Graph Memory for Claude (Design)

**Status:** draft v1 · 2026-07-11
**Owner:** Muhammed Sezer · built with Claude
**Two layers, strictly separated:**
- **Tool (open-source):** a generic knowledge-graph memory MCP server. No personal data in the repo, ever.
- **Data (private):** your own graph, hosted on your Always Free Oracle Autonomous AI Database 26ai. Lives entirely in your database — never in this repo.

## 1. Goals

1. A single, ever-growing, well-defined memory: github, design, plans, engineering, ideas, saas, env, … — open-ended domains.
2. Everything interlinked → a large weighted graph Claude can *walk* ("Markov chain" retrieval: from any node, hop to related knowledge with edge weights as transition strength).
3. Claude uses it effortlessly via MCP: remember, recall, search, traverse, organize — and the tool *enforces* librarian discipline (dedup, linking, maintenance) so the graph compounds instead of rotting.
4. Shareable: anyone can run it with zero setup (SQLite) or free cloud (Oracle ADB).

## 2. Architecture

```
Claude (any client) ──MCP──▶ graphmem server (Python)
                               ├─ Store adapter (pluggable)
                               │    ├─ SQLiteStore   (default; sqlite-vec)     ← OSS zero-setup
                               │    ├─ OracleStore   (ADB 26ai; native VECTOR, in-DB ONNX)  ← Sezer
                               │    └─ PostgresStore (pgvector)                ← later
                               └─ Embedder abstraction
                                    ├─ Oracle in-DB ONNX (DBMS_VECTOR, e.g. all-MiniLM-L12-v2) — no external API
                                    └─ Local sentence-transformers / sqlite path for non-Oracle stores
```

- Language: Python 3.12, `mcp` SDK, `python-oracledb` (thin, arm64-safe).
- License: MIT. Repo: github.com/sezer-muhammed/graphmem.
- Config via env: `GRAPHMEM_STORE=sqlite|oracle|postgres` + store-specific vars (wallet dir, DSN, …).

## 3. Data model

### 3.1 `node` — everything is a node

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| name | unique slug | stable handle, e.g. `oracle-free-tier-cut` |
| domain | text (open, registry-checked) | github · design · plan · engineering · ideas · saas · env · … unbounded |
| kind | text (open, registry-checked) | repo · project · plan · idea · service · decision · snippet · doc · person · task · reference · … |
| title | text | short human title |
| summary | text | 1–3 sentences; **embedding is computed from title+summary+tags, not body** (long bodies dilute vectors) |
| body | CLOB/text | full content, fetched via `get`, not returned in list results |
| attrs | JSON | kind-specific fields (repo→url/lang; service→host/port; saas→pricing) |
| tags | JSON array | |
| aliases | JSON array | "PostgreSQL" = "postgres" = "pg"; used by resolver + dedup |
| status | active · wip · idea · archived | |
| sensitivity | public · private · secret | `export` filters; `secret` bodies never leave the store unredacted |
| source | text | where this came from (conversation, url, file, inference) |
| confidence | 0–1 | how sure we are it's true |
| last_verified | timestamp | staleness signal (facts rot — e.g. Oracle 4→2 OCPU) |
| created_at / updated_at | timestamps | |
| embedding | VECTOR | Oracle native VECTOR / sqlite-vec blob |

### 3.2 `edge` — typed, directed, weighted (the Markov chain)

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| src, dst | FK→node | directed |
| rel | text (registry-checked) | relates_to · depends_on · part_of · uses · implements · inspired_by · deployed_on · references · supersedes · blocks · … |
| weight | 0–1 | transition strength for walks. v1: default 0.5, manual override allowed. v2: **learned** — co-recall reinforcement (edges between nodes retrieved together get strengthened; slow decay elsewhere) |
| note | text | why these are connected |
| created_at / last_reinforced | timestamps | |

Registry defines which rels are symmetric (relates_to) vs directed with inverse names (part_of ↔ has_part); traversal respects direction and can filter by rel class (structural vs soft).

### 3.3 `vocabulary` — open but consistent

One table registering every `domain`, `kind`, `rel` value in use (+ description, + inverse for rels). Anything can be added at any time (**no schema migration ever**), but writes normalize against it: near-miss values ("Github", "gh") resolve to the canonical entry instead of forking the vocabulary. This is the entropy guard for an unbounded, growing graph.

### 3.4 `access_log` (v2)

(node_id, ts, query_id) — fuel for learned edge weights and for `review` (never-accessed nodes are prune candidates).

## 4. Retrieval — three modes, composable

1. **Semantic** — `VECTOR_DISTANCE(embedding, :q, COSINE)` over title+summary+tags vectors.
2. **Keyword** — Oracle Text / FTS5 index over title, summary, body.
3. **Graph walk** — from seed node(s), follow edges by `weight × rel-filter × direction`, depth 1–3. This is the Markov traversal: weights are transition probabilities, so recall naturally flows to what's *actually related in practice*.

Default `recall` = semantic top-k **+ 1-hop neighborhood** of the top hits (compact: id, name, title, summary, why-matched, edge context). Claude scans, then `get`s deep.

## 5. MCP tools

| tool | behavior |
|---|---|
| `remember` | **Dedup-first:** embeds the candidate, shows near-duplicates, offers update/link instead of insert. Normalizes domain/kind via vocabulary. Auto-suggests links to nearest existing nodes ("connect these?"). |
| `recall` | semantic + neighborhood (see §4) |
| `search` | keyword/filter (domain, kind, tag, status, date) |
| `get` | full node incl. body + all edges |
| `link` / `unlink` | create/remove typed edge; validates rel against registry |
| `walk` | explicit graph traversal from a node (depth, rel filter, min weight) |
| `update` | patch fields; bumps updated_at; re-embeds if title/summary/tags changed |
| `forget` | archive (default) or hard-delete |
| `merge` | fold node B into A: move edges, union aliases/tags, keep provenance |
| `review` | maintenance queue: stale (`last_verified` old), low-confidence, orphan (no edges), never-accessed |
| `vocab` | list/add/describe domains, kinds, rels |
| `export` / `import` | JSON dump/load, sensitivity-filtered (secret redacted by default) |

Design rule: **list-like outputs are compact** (no bodies) to keep token cost low; depth is opt-in via `get`.

## 6. Security

- `env` domain stores *topology and references*, never plaintext secrets. Real secrets → OCI Vault or encrypted at rest; nodes hold pointers.
- `sensitivity=secret` nodes: body excluded from `export` and from any shared/OSS demo fixtures.
- Oracle connection: mTLS wallet, credentials in `~/.graphmem/.env` (mode 600).
- ADB network ACL: "secure access from everywhere" + mTLS by default; tighten to a specific source IP/VCN if you want.

## 7. Ops (self-hosting)

- **Keep-alive:** Always Free ADB auto-stops after 7 idle days (reclaimed ~90 days stopped). Daily cron: `python -m graphmem.keepalive`. With `ADB_OCID` set and the `oci` extra installed, instance-principal / CLI auth additionally allows programmatic start if it ever stops.
- **Monitoring/management:** OCI Python SDK with an instance principal or CLI config (`manage autonomous-databases`).
- **Backups:** ADB automatic (60-day retention). Optionally cron `graphmem export` to Object Storage for belt-and-braces.

## 8. Roadmap

- **v1 (now):** Oracle store + SQLite store, schema above, ONNX in-DB embeddings, MCP tools minus learned weights (`weight` manual/default), keep-alive cron, seed the graph from existing local memory/notes.
- **v1.1:** dedup/auto-link polish, `review`, `merge`, export→Object Storage.
- **v2:** learned edge weights (co-recall reinforcement + decay), access_log, Postgres adapter, property-graph queries (GRAPH_TABLE) where available, public README + examples + demo fixture.

## 9. Open questions

- Repo name (graphmem?) and whether embedder model ships pinned or downloadable.
- Reinforcement formula for v2 weights (simple additive w/ decay vs Bayesian).
- Whether MCP runs as long-lived server (systemd) or stdio-per-session (start with stdio; systemd later if latency hurts).
