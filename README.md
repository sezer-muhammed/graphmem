# graphmem 🧠

**Knowledge-graph memory for Claude** — an MCP server + CLI backed by a free-forever
Oracle Autonomous Database. Everything you tell Claude to remember becomes a node in
one ever-growing, interlinked graph: semantic recall (vector search), keyword search,
and weighted graph traversal ("Markov walk") over typed edges.

- **Embeddings run inside the database** (ONNX all-MiniLM-L12-v2, 384-dim, via
  `DBMS_VECTOR`) — no OpenAI key, no local model, no external API. Free, private, durable.
  The model is English-centric, so **phrase `recall` queries in English** for best
  results (use `search` for exact non-English terms). Swappable for a multilingual
  ONNX model — see DESIGN.md.
- **Dedup-first writes:** `remember` refuses near-duplicates and suggests linking instead.
- **Auto-link suggestions:** every save proposes related nodes, so the graph stays a graph.
- **Open vocabulary:** domains/kinds/rels are data, not schema — grow them forever with
  zero migrations, guarded against `github`/`Github`/`gh` entropy.

```
Claude (MCP) ─┐
CLI ──────────┼──▶ graphmem.core ──▶ Oracle ADB 26ai (Always Free, 20 GB)
Web explorer ─┘                       ├─ node (VECTOR embedding, provenance)
                                      ├─ edge (typed, directed, weighted)
                                      └─ vocabulary (open, consistent)
```

## Repo layout

```
src/graphmem/
  core.py       all operations (shared by every interface)
  server.py     MCP server (stdio)         → python -m graphmem.server
  cli.py        CLI                        → graphmem <cmd>
  webapp.py     graph explorer web UI      → python -m graphmem.webapp
  keepalive.py  daily DB touch + auto-start→ python -m graphmem.keepalive
  initdb.py     fresh-DB setup (schema + ONNX model)
  schema.sql
DESIGN.md       full design doc (data model, retrieval, roadmap)
.env.example    connection template — copy to .env (never committed)
```

## Setup from zero (one-time, ~15 min)

You need a free Oracle Cloud account (no paid resources are ever created).

1. **Create the database** — OCI Console → Oracle Database → Autonomous Database →
   Create. Pick: workload **Transaction Processing**, deployment **Serverless**,
   ☑ **Always Free**, version **26ai** (or 23ai — anything with VECTOR),
   ☑ **Require mTLS**, network access "Secure access from everywhere".
   Set the ADMIN password. Wait ~4 min for *Available*.
   - Via API instead? **Pin `db_version`** — the API default is 19c, which has no
     VECTOR support.
2. **Download the wallet** — DB page → Database connection → Download wallet, set a
   wallet password. Unzip it somewhere private (e.g. `./wallet/`, git-ignored).
3. **Configure** — `cp .env.example .env`, fill in the ADMIN password, wallet dir
   (absolute path), wallet password. DSN `<dbname>_low` is in the wallet's
   `tnsnames.ora` (e.g. `mydb_low`).
4. **Install + initialize**
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -e .
   .venv/bin/graphmem init-db     # applies schema + loads the ONNX embed model
   .venv/bin/graphmem stats       # should print an empty-but-valid graph
   ```

## Connect Claude Code (any machine)

### Easiest: install as a Claude Code plugin (bundles MCP + skill + /setup)

```bash
claude plugin marketplace add sezer-muhammed/graphmem
claude plugin install graphmem@graphmem
```

That registers the `graphmem` MCP automatically (runs via `uv`, no venv needed),
loads a **usage skill** (teaches Claude the librarian discipline), and adds
**`/graphmem:setup`** which walks through wallet + `.env` provisioning into the
standard per-user location **`~/.graphmem/`** (`.env` + `wallet/`). Config
resolution order: `$GRAPHMEM_ENV` → `~/.graphmem/.env` → repo root.

### Repo-local (this project dir only)

The repo ships a `.mcp.json` — opening this directory in Claude Code offers the
`graphmem` server automatically (also via `uv`).

### Classic (manual, venv)

```bash
claude mcp add --scope user graphmem /abs/path/to/.venv/bin/python -- -m graphmem.server
```

New Claude Code sessions now expose the tools: `remember` · `recall` · `search` ·
`get` · `link` · `walk` · `update` · `forget` · `vocab` · `stats`.
Try: *"hafızanda sunucuyla ilgili ne var?"* → Claude calls `recall`.

### Second machine (e.g. laptop) — same brain, 5 minutes

The database is in the cloud; every machine you connect sees the same memory.

```bash
git clone git@github.com:sezer-muhammed/graphmem.git && cd graphmem
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env            # fill in as in step 3 above
# wallet: download a fresh one from the OCI Console (or scp the dir from the server)
.venv/bin/graphmem stats        # ✓ you should see the existing graph
claude mcp add --scope user graphmem $PWD/.venv/bin/python -- -m graphmem.server
```

Then in Claude Code on that machine: *"import the notes in ~/foo into memory"* —
Claude reads local files and calls `remember`/`link`; everything lands in the shared graph.

## CLI cheatsheet

```bash
graphmem recall "how do I reopen the website"      # semantic
graphmem search --domain env                       # filters
graphmem get my-server                             # full node + edges
graphmem remember my-idea ideas idea "Title" "Summary" --tags x,y
graphmem link my-idea some-project relates_to -w 0.7
graphmem walk graphmem-project -d 2                # Markov walk
graphmem vocab                                     # domains/kinds/rels
graphmem stats                                     # health overview
graphmem export -o backup.json                     # portable full dump
graphmem import backup.json                        # merge into another DB
```

## Web explorer

```bash
.venv/bin/pip install -e '.[web]'
GRAPHMEM_WEB_HOST=127.0.0.1 GRAPHMEM_WEB_PORT=8090 .venv/bin/python -m graphmem.webapp
```

Force-directed graph of the whole memory (colored by domain, edge width = weight),
click any node for details, search (keyword + semantic), and **walk mode**: hop
node-to-node along weighted edges with a breadcrumb trail.

Optional HTTP Basic auth: set `GRAPHMEM_WEB_USER` + `GRAPHMEM_WEB_PASSWORD` in
`.env` (or the environment). Unset = open, for localhost use.

## Operational notes

- **Always Free ADB auto-stops after 7 idle days** (reclaimed after ~90 days stopped).
  Cron `python -m graphmem.keepalive` daily; with `ADB_OCID` set and the `oci` extra
  installed it also auto-starts a stopped DB (OCI instance principal or CLI config).
- Backups: ADB does automatic backups (60-day retention) — your memory outlives the machine.
- **Never commit `.env` or `wallet/`** — both are git-ignored. The wallet + password
  = full DB access.
- Secrets don't belong in node bodies. Store *pointers* (what/where), keep credentials
  in a vault. `sensitivity=secret` nodes are for extra-careful metadata, not passwords.

## License

MIT — see [LICENSE](LICENSE). **v1.0.0** (2026-07-19) is the first stable release;
see [CHANGELOG.md](CHANGELOG.md). A SQLite adapter for zero-setup local use is on the
roadmap (DESIGN.md §8); today the backend is a free Oracle Autonomous Database.

A visual **console** with an AI copilot (Claude Haiku, grounded in your graph) lives
at graphmem.sezer.ai — the graph you can see and steer, not just a library.
