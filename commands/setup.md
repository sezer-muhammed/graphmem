---
description: Set up graphmem on this machine — config, wallet, connection check, MCP verification
---

Set up graphmem (a knowledge-graph memory backed by an Oracle Autonomous Database) on this machine:

1. Check prerequisites: `uv` (or python3.10+), and whether `~/.graphmem/.env` already exists. If it exists, skip to step 4.
2. Create the standard config dir: `mkdir -p ~/.graphmem && chmod 700 ~/.graphmem`.
3. Provide the connection config and wallet:
   - **First machine / new database?** Follow README "Setup from zero" to create a free Oracle ADB and download its wallet, then `cp .env.example ~/.graphmem/.env` and fill in the values.
   - **Adding another device to an existing graph?** Copy your own `~/.graphmem/.env` and `~/.graphmem/wallet/` from a machine that already works (e.g. `scp -r you@your-host:~/.graphmem/wallet ~/.graphmem/wallet`), or download a fresh wallet for the same database from the OCI Console.
   - Edit `~/.graphmem/.env`: set `ADB_WALLET_DIR` to this machine's absolute `~/.graphmem/wallet` path. `chmod 600 ~/.graphmem/.env`.
4. Verify the DB connection: run `uv run --with <plugin-or-repo-root> python -m graphmem.cli stats` (or `.venv/bin/graphmem stats` for a repo install). Expect a valid graph summary. If it times out, an Always Free ADB may be idle-stopped — run `python -m graphmem.keepalive` (auto-starts with `ADB_OCID` set) or start it from the OCI Console.
5. Verify the MCP tools are live in this session (try `stats`).
6. Report: connection status, node count, and whether any further onboarding is needed.
