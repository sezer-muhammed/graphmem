# Changelog

## 1.0.0 — 2026-07-19

First stable release. graphmem now ships an MCP server, a CLI, a web graph
explorer, and (separately) a visual **console** with an AI copilot at
graphmem.sezer.ai.

### Security
- **Consistent secret redaction.** `sensitivity=secret` nodes never leak their
  `body` or `attrs` through any surface. New `core.redact_secret()` helper is
  applied to the web explorer's `/api/node` (previously only `attrs` was masked,
  leaving `body` exposed), and `export_graph()` now masks secret `attrs` too, not
  just `body`.
- **Web explorer fails closed.** Setting only one of `GRAPHMEM_WEB_USER` /
  `GRAPHMEM_WEB_PASSWORD` now raises at startup instead of silently serving with
  no authentication.

### Robustness
- **Graceful DB-unavailable.** An unreachable database now raises a clear
  `core.DBUnavailable` with a recovery hint (the Always-Free ADB may be waking
  from idle) instead of a raw driver traceback.
- **`remember()` no longer crashes on a duplicate node name** — it returns a
  friendly error suggesting `update` or a different name.
- **Hardened `.env` handling.** Parsing strips surrounding quotes/whitespace,
  `connect()` validates the required keys up front, and all file reads are UTF-8
  (fixes cp1252 mojibake on Windows second machines).

### Added
- Web explorer **Tables** and **Diagram** views alongside the force-graph.
- `graphmem --version` and `graphmem.__version__`.
- A **non-destructive unit-test suite** (`tests/test_core.py`) — pure helpers +
  a mocked cursor for the vocab guard; requires no database, network, or wallet.

### Deferred to 1.1
- The module-level shared DB connection is single-connection; a proper connection
  pool for concurrent web workers is planned.
- `import_graph` transactional rollback on mid-import failure.

## 0.1.0
- Initial knowledge-graph memory MCP + CLI (Oracle ADB backend, in-DB ONNX
  embeddings, force-graph web explorer, export/import, Claude Code plugin).
