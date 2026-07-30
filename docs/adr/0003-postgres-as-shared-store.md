---
status: accepted
---

# Postgres as the single shared store, replacing SQLite

The project currently persists to two SQLite files (`squadrons_reference.db`, `squadrons_stats.db`), which is fine for a single interactive CLI operator but not for a containerized backend where a score bot, an ingestion API, and stats/ELO logic may run as separate concurrent processes — SQLite's single-writer file locking becomes a bottleneck and a source of corruption risk under concurrent Discord-triggered writes. We're moving all canonical state (reference teams/players, matches, player_stats, and derived ELO/report data) into a single Postgres instance, run as its own container in docker-compose. This also matches the sibling ontology-rag project, which already runs Postgres+pgvector, keeping the operational footprint (backup, connection pooling, migrations tooling) consistent across projects even though the databases themselves are separate.

**Consequences:** existing scripts that open a SQLite file directly need a data-access layer swapped to Postgres (connection string/pooling, schema migrations instead of ad-hoc `CREATE TABLE IF NOT EXISTS`). Existing `.db` files and their data need a one-time migration if historical match/reference data is to be preserved.
