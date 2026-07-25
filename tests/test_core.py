"""Non-destructive unit tests for graphmem.core.

These NEVER touch the real Oracle ADB: they exercise the pure helper functions
and use a tiny fake cursor for the vocabulary-guard logic. Run either with
pytest (`pytest -q`) or standalone (`python tests/test_core.py`) — no DB, no
network, no credentials required.
"""
import decimal
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graphmem import core  # noqa: E402
from graphmem.context import GraphContext, local_single_user_context  # noqa: E402

CTX = GraphContext("tenant-a", "graph-a", "user-a")


# ------------------------------------------------------------- pure helpers --
def test_plain_converts_decimal_and_nested():
    assert core.plain(decimal.Decimal("3")) == 3
    assert isinstance(core.plain(decimal.Decimal("3")), int)
    assert core.plain(decimal.Decimal("2.5")) == 2.5
    assert core.plain({"a": decimal.Decimal("1"), "b": [decimal.Decimal("2")]}) == {"a": 1, "b": [2]}
    assert core.plain("x") == "x"


def test_jval_parses_json_only_when_valid():
    assert core.jval('{"a": 1}') == {"a": 1}
    assert core.jval("[1, 2]") == [1, 2]
    assert core.jval("not json") == "not json"
    assert core.jval(None) is None
    assert core.jval("") == ""


def test_embed_text_shapes():
    assert core.embed_text("Title", "Summary", ["a", "b"]) == "Title — Summary — tags: a, b"
    assert core.embed_text("Title", "", None) == "Title"
    assert core.embed_text("Title", "Summary", None) == "Title — Summary"
    assert core.embed_text("", "", None) == ""


def test_node_row_parses_json_columns_and_lowercases():
    cols = ["NAME", "ATTRS", "TAGS"]
    row = ("foo", '{"port": 80}', '["x", "y"]')
    out = core.node_row(row, cols)
    assert out["name"] == "foo"
    assert out["attrs"] == {"port": 80}
    assert out["tags"] == ["x", "y"]


# ---------------------------------------------------- secret redaction guard --
def test_redact_secret_masks_body_and_attrs():
    node = {"name": "cred-x", "sensitivity": "secret", "title": "T",
            "summary": "S", "body": "TOP SECRET", "attrs": {"key": "AKIA..."}}
    core.redact_secret(node)
    assert node["body"] == "[redacted — secret node]"
    assert node["attrs"] == {"_redacted": True}
    # non-sensitive fields stay visible
    assert node["title"] == "T" and node["summary"] == "S"


def test_redact_secret_leaves_non_secret_untouched():
    node = {"name": "n", "sensitivity": "private", "body": "visible",
            "attrs": {"port": 80}}
    core.redact_secret(node)
    assert node["body"] == "visible"
    assert node["attrs"] == {"port": 80}


def test_redact_secret_handles_missing_fields():
    node = {"name": "n", "sensitivity": "secret"}          # no body/attrs
    core.redact_secret(node)                                 # must not raise
    assert node.get("body") is None


def test_redact_secret_is_noop_on_non_dict():
    assert core.redact_secret(None) is None
    assert core.redact_secret({"error": "x"}) == {"error": "x"}


# ----------------------------------------------- vocab guard (mocked cursor) --
class FakeCursor:
    """Minimal cursor stand-in: returns a fixed vocabulary for any query."""
    def __init__(self, values):
        self._values = values
        self._rows = []
        self.sql = ""
        self.binds = {}

    def execute(self, sql, **binds):
        self.sql = sql
        self.binds = binds
        self._rows = [(v,) for v in self._values]

    def fetchall(self):
        return self._rows


def test_check_vocab_exact_case_insensitive_and_miss():
    cur = FakeCursor({"env", "engineering", "github"})
    assert core.check_vocab(CTX, cur, "domain", "env") == (True, "env")
    # case-insensitive canonicalization back to the stored value
    assert core.check_vocab(CTX, cur, "domain", "GitHub") == (True, "github")
    # genuine miss
    ok, canon = core.check_vocab(CTX, cur, "domain", "nope")
    assert ok is False and canon is None


def test_vocab_values_returns_a_set():
    cur = FakeCursor(["a", "b", "a"])
    assert core.vocab_values(CTX, cur, "domain") == {"a", "b"}
    assert "tenant_id=:tenant_id" in cur.sql
    assert "graph_id=:graph_id" in cur.sql
    assert cur.binds == {"tenant_id": "tenant-a", "graph_id": "graph-a",
                         "c": "domain"}


def test_graph_context_is_validated_and_hashable():
    assert CTX.binds() == {"tenant_id": "tenant-a", "graph_id": "graph-a"}
    assert len({CTX, GraphContext("tenant-a", "graph-a", "user-a")}) == 1
    for values in (("", "g", "u"), ("Tenant A", "g", "u"), ("t", "../g", "u")):
        try:
            GraphContext(*values)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe graph context identifier accepted")


def test_core_rejects_missing_or_unverified_context_before_db_access():
    for bad in (None, {}, "tenant-a"):
        try:
            core._scope(bad)
        except TypeError as exc:
            assert "GraphContext" in str(exc)
        else:
            raise AssertionError("unverified context accepted")


def test_local_adapter_uses_explicit_environment(monkeypatch):
    monkeypatch.setenv("GRAPHMEM_TENANT_ID", "local-tenant")
    monkeypatch.setenv("GRAPHMEM_GRAPH_ID", "work")
    monkeypatch.setenv("GRAPHMEM_PRINCIPAL_ID", "local-agent")
    assert local_single_user_context() == GraphContext(
        "local-tenant", "work", "local-agent")


# -------------------------------------------------------------- standalone ----
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f" FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
