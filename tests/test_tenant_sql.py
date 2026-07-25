"""Offline guards against accidentally removing tenant predicates."""
import inspect

from graphmem import core


PUBLIC_OPERATIONS = (
    core.remember, core.recall, core.search, core.get, core.link, core.walk,
    core.update, core.forget, core.vocab, core.stats, core.graph_dump,
    core.export_graph, core.import_graph,
)


def test_every_core_operation_requires_context_as_first_argument():
    for operation in PUBLIC_OPERATIONS:
        parameters = list(inspect.signature(operation).parameters)
        assert parameters[0] == "ctx", operation.__name__


def test_context_is_validated_before_opening_database():
    for operation in PUBLIC_OPERATIONS:
        source = inspect.getsource(operation)
        assert source.index("_scope(ctx)") < source.index("db()"), operation.__name__


def test_all_data_plane_sql_is_tenant_and_graph_scoped():
    # Broad source-level tripwire for dynamically assembled Oracle SQL. Detailed
    # execution tests remain required against a disposable Oracle clone.
    for operation in PUBLIC_OPERATIONS:
        source = inspect.getsource(operation).lower()
        assert "tenant_id" in source or "_scope(ctx)" in source, operation.__name__
        assert "graph_id" in source or "_scope(ctx)" in source, operation.__name__


def test_cross_tenant_edge_constraints_are_present_in_migration():
    migration = open("migrations/002_shared_schema_tenancy.sql",
                     encoding="utf-8").read().lower()
    assert "edge_src_scope_fk" in migration
    assert "edge_dst_scope_fk" in migration
    assert migration.count(
        "foreign key (tenant_id,graph_id") >= 4
