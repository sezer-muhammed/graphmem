#!/usr/bin/env python3
"""graphmem MCP server — thin wrapper around graphmem.core.

Run: python -m graphmem.server   (stdio transport)
"""
import json

from mcp.server.fastmcp import FastMCP

from . import core
from .context import local_single_user_context

mcp = FastMCP("graphmem")
_CTX = local_single_user_context()


@mcp.tool()
def remember(name: str, domain: str, kind: str, title: str, summary: str,
             body: str = "", tags: list[str] | None = None,
             attrs: dict | None = None, aliases: list[str] | None = None,
             sensitivity: str = "private", source: str = "conversation",
             confidence: float = 0.8, force: bool = False) -> str:
    """Store a new memory node. Checks for near-duplicates first (returns them
    instead of inserting unless force=true) and suggests related nodes to link.
    name: unique kebab-case slug. domain/kind must exist in vocabulary (use the
    vocab tool to list/add). summary: 1-3 sentences (drives semantic recall)."""
    return json.dumps(core.remember(_CTX, name, domain, kind, title, summary, body,
                                    tags, attrs, aliases, sensitivity, source,
                                    confidence, force))


@mcp.tool()
def recall(query: str, k: int = 5, domain: str = "",
           include_neighbors: bool = True) -> str:
    """Semantic recall: find the k most relevant nodes for a natural-language
    query, plus (by default) their 1-hop graph neighborhood for context.
    ALWAYS phrase `query` in ENGLISH — the embedding model is English-centric,
    so non-English queries retrieve poorly even when node content is about the
    same thing. For an exact non-English term, use `search` (keyword) instead."""
    return json.dumps(core.recall(_CTX, query, k, domain, include_neighbors))


@mcp.tool()
def search(text: str = "", domain: str = "", kind: str = "", status: str = "",
           limit: int = 20) -> str:
    """Keyword/filter search over name, title, summary, aliases (case-insensitive
    substring). Combine with domain/kind/status filters. For meaning-based
    lookup use recall instead."""
    return json.dumps(core.search(_CTX, text, domain, kind, status, limit))


@mcp.tool()
def get(name: str) -> str:
    """Fetch one node in full (body, attrs, provenance) plus all its edges."""
    return json.dumps(core.get(_CTX, name))


@mcp.tool()
def link(src: str, dst: str, rel: str, weight: float = 0.5, note: str = "") -> str:
    """Create a typed, directed, weighted edge between two nodes (by name).
    rel must exist in vocabulary (e.g. relates_to, depends_on, part_of, uses,
    supersedes). weight 0-1 = traversal strength."""
    return json.dumps(core.link(_CTX, src, dst, rel, weight, note))


@mcp.tool()
def walk(start: str, depth: int = 2, min_weight: float = 0.0, rel: str = "") -> str:
    """Traverse the graph from a node (both directions), following edges with
    weight >= min_weight, optionally only a given rel. Returns nodes by hop
    distance — the 'Markov walk' view of related knowledge."""
    return json.dumps(core.walk(_CTX, start, depth, min_weight, rel))


@mcp.tool()
def update(name: str, title: str = "", summary: str = "", body: str = "",
           status: str = "", confidence: float = -1.0,
           add_tags: list[str] | None = None, attrs: dict | None = None,
           verified: bool = False) -> str:
    """Patch fields of an existing node. Only non-empty args are applied.
    verified=true stamps last_verified=now. Re-embeds if title/summary/tags change."""
    return json.dumps(core.update(_CTX, name, title, summary, body, status,
                                  confidence, add_tags, attrs, verified))


@mcp.tool()
def forget(name: str, hard: bool = False) -> str:
    """Archive a node (default) or hard-delete it and its edges (hard=true)."""
    return json.dumps(core.forget(_CTX, name, hard))


@mcp.tool()
def vocab(action: str = "list", category: str = "", value: str = "",
          description: str = "", inverse_rel: str = "") -> str:
    """Manage the open vocabulary of domains/kinds/rels.
    action='list' (optionally filter by category) or action='add'
    (category+value+description required; inverse_rel for directed rels)."""
    return json.dumps(core.vocab(_CTX, action, category, value, description, inverse_rel))


@mcp.tool()
def stats() -> str:
    """Graph overview: node counts by domain/kind/status, edge counts by rel,
    orphan nodes (no edges), stale nodes (last_verified > 90 days or never)."""
    return json.dumps(core.stats(_CTX))


@mcp.tool()
def export(include_secret: bool = False) -> str:
    """Dump the whole graph (nodes+edges+vocabulary) as portable JSON
    (graphmem-export-v1). secret bodies redacted unless include_secret."""
    return json.dumps(core.export_graph(_CTX, include_secret))


if __name__ == "__main__":
    mcp.run()
