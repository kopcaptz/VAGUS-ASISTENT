# Performance Tuning

## API Key Validation Path

Phase 2 introduces two controls to keep validation overhead predictable:

- cache TTL: 15 minutes
- cache capacity: LRU max 100 entries

Validation cache key includes key name, provider type, validation mode, and value hash.

## Rate Limiting

Validation requests are rate-limited per `key/provider` pair.

- default minimum interval: 2 seconds
- if the limit is exceeded, validation returns a retry-later error

## Router Key Lookup Cache

`ProviderFactory` keeps in-memory API key cache:

- TTL: 300 seconds
- invalidated on key change events

This avoids repeated secure-store reads on hot paths while still reacting quickly to key updates.

## Benchmark Guidance

For no-regression checks:

1. Baseline one uncached validation call.
2. Run repeated validations in cache window.
3. Assert hot calls avoid network probes and complete faster.
4. Verify cache invalidation on key update/delete.
