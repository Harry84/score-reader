---
status: accepted
---

# Dedicated Postgres instance, not shared with the campaign/ontology-rag project

The sibling campaign-layer project also runs Postgres (reusing the instance already running for its ontology-rag/pgvector service) and could, in principle, host this project's tables too. We chose a fully separate, dedicated Postgres container for this project instead — even for local single-machine development now, with cloud hosting as a later possibility. The two schemas never need to join to each other; the only integration point between the two projects is the HTTP webhook/read-API boundary already decided in ADR-0001, so there's no technical reason to co-locate the data. Sharing an instance would couple migration, backup, and connection-pool lifecycle across two independently-developed repos, and — since both bots ingest untrusted user content from Discord — would let a compromise of one service's DB credentials reach the other project's data. Running a second small Postgres container costs nothing meaningful, and cloud-managed Postgres is normally provisioned per-service anyway.

**Consequences:** this repo's docker-compose owns its own Postgres container end to end (schema, migrations, backups). Nothing here depends on the campaign project's database being reachable.
