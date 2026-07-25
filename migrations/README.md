# Oracle ADB migrations

These files are operator-reviewed migration designs, not application startup
hooks. Never run them implicitly.

`002_shared_schema_tenancy.sql` is staged and restart-safe:

1. creates identity/control tables if absent;
2. adds nullable discriminator columns;
3. creates/backfills the founder's legacy tenant and graph;
4. validates orphan and cross-scope invariants;
5. replaces global uniqueness with tenant-scoped constraints;
6. makes discriminators non-null and installs composite foreign keys.

Before production use: take a verified export/backup, test against a clone,
record the migration in `schema_migration`, deploy tenant-scoped application
code before admitting new tenants, and verify rollback/restore. The script is
provided for review only and has not been executed against any database.
