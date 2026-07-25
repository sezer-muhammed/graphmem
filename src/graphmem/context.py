"""Tenant identity carried from a trusted authentication boundary to SQL.

Network handlers must construct ``GraphContext`` from a verified session or
API token. Client-controlled tool arguments and request payloads must never
select the tenant or graph.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class GraphContext:
    tenant_id: str
    graph_id: str
    principal_id: str

    def __post_init__(self) -> None:
        for field in ("tenant_id", "graph_id", "principal_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(f"invalid {field}")

    def binds(self) -> dict[str, str]:
        return {"tenant_id": self.tenant_id, "graph_id": self.graph_id}


def local_single_user_context() -> GraphContext:
    """Explicit compatibility adapter for trusted local CLI/stdio MCP use.

    Hosted services must not call this function. They inject a context derived
    from authentication instead. The defaults identify the one pre-tenancy
    graph and are the values used by the staged backfill migration.
    """
    return GraphContext(
        tenant_id=os.environ.get("GRAPHMEM_TENANT_ID", "legacy-local"),
        graph_id=os.environ.get("GRAPHMEM_GRAPH_ID", "default"),
        principal_id=os.environ.get("GRAPHMEM_PRINCIPAL_ID", "local-user"),
    )
