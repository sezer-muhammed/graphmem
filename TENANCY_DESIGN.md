# Shared-schema tenancy foundation

Status: implementation foundation; not production-ready and not migrated.

## Trust boundary

The hosted API/MCP gateway authenticates a browser session or opaque API
token, resolves membership server-side, and constructs:

```python
GraphContext(tenant_id="...", graph_id="...", principal_id="...")
```

Tenant and graph identifiers are never accepted from MCP tool arguments,
request bodies, model output, URL parameters, or forwarding headers. Core
operations require this context as their first argument. The local CLI and
stdio MCP use the deliberately named `local_single_user_context()` adapter;
hosted code must not use it.

## Database isolation

One least-privilege Oracle application account accesses one shared schema.
Every node, edge, and vocabulary row carries `tenant_id` and `graph_id`.
Names and vocabulary are unique inside a graph, not globally. Edges repeat the
scope and both endpoints use composite foreign keys to scoped node identities,
so Oracle rejects cross-tenant/cross-graph edges.

All current data-plane SQL binds both discriminators, including vector dedup
and recall, neighbor traversal, stats, exports, and imports. A later hardening
stage should add Oracle application context and VPD policies, with pool
checkout/checkin tests proving context cannot leak between requests.

## Migration and rollout

`migrations/002_shared_schema_tenancy.sql` is a manually reviewed staged
design. It creates control-plane tables, adds nullable columns, backfills the
legacy graph, validates edge scope, replaces global uniqueness, then enforces
non-null composite constraints. It has not been run.

Required rollout:

1. verified backup and restore rehearsal;
2. disposable ADB clone migration twice (idempotency);
3. deploy context-aware engine and gateway in maintenance mode;
4. run migration and isolation probes;
5. enable founder traffic, then test tenants, then customers;
6. retain a restore-based rollback because Oracle DDL auto-commits.

## Remaining hosted integration

- OIDC user provisioning, memberships, graph selection, session lifecycle;
- hashed opaque API-token storage, scopes, rotation, revocation, last-used;
- Streamable HTTP MCP gateway that injects `GraphContext`;
- durable usage ledger, quotas, billing and audit events;
- Oracle connection pool and optional VPD;
- disposable-Oracle integration and concurrency tests;
- deletion/export/retention workflows.

## Threat-model questions for cross-review

- Can any onboarding callback choose or overwrite a tenant before issuer,
  subject, nonce, state, and PKCE are verified?
- Does account linking rely on mutable email rather than issuer + subject?
- Are API tokens displayed once, stored only as a keyed digest, scope-limited,
  revocable, and prevented from selecting another tenant?
- Can an MCP client smuggle `tenant_id` through tool JSON, headers, prompts, or
  import payloads?
- Can a pooled Oracle session retain another request's application context?
- Does graph creation/member invitation enforce plan limits transactionally?
- Can demo credentials or cookies reach a customer-backed graph?
- Can retries double-create users, graphs, usage events, or billing records?
- Does migration rehearsal verify same-name nodes in different tenants,
  cross-scope RAW IDs, imports/exports, and restore time before production?
