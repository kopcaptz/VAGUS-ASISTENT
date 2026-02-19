# Plugin System in Production

## Deployment topology

`docker-compose.yml` includes:

- `api` service,
- `marketplace` service,
- `dashboard`,
- `telegram-bot` (profile-based),
- `prometheus` for metrics.

## Recommended settings

In production:

- enable sandbox and security restrictions,
- require digital signatures for plugins,
- enforce resource quotas and rate limits per plugin,
- monitor plugin metrics and disable unhealthy plugins automatically.

## Security hardening

Use `PluginSecurityHardening`:

- signature policy checks,
- plugin rate limiting,
- memory/execution quotas,
- audit trail for plugin operations.

## Lifecycle and upgrades

- manage plugin states with `PluginLifecycleManager`,
- run config migrations via `PluginMigrationManager`,
- create backup before migration,
- rollback on migration failure.

## Observability

Prometheus scrapes:

- API metrics (`api:8000/metrics`),
- marketplace metrics (`marketplace:9000/metrics`).
