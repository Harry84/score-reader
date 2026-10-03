---
status: accepted
---

# Coarse-grained service split: Postgres, one backend API, one score bot

Despite `score_extractor` already existing as a standalone Azure Function (suggesting a service-per-script pattern), we're deliberately keeping this repo to three containers: Postgres, a single backend API (team management, screenshot ingestion/extraction, stats, ELO — all as routes in one app), and the score bot. A fine-grained split (separate extraction service, separate stats/ELO service, separate reference/team-admin service) would add inter-service HTTP calls and independent failure modes for logic that is almost always exercised together in one request (a screenshot lands → extract → resolve identities → persist → recompute stats/ELO). Keeping it one deploy unit makes that pipeline easier to reason about and test end-to-end, at the cost of not being able to scale or deploy pieces of it independently later.

**Consequences:** internal module boundaries inside the backend API (extraction, reference/identity resolution, match persistence, stats/ELO) must still be kept clean, since this decision is reversible — splitting a well-factored module out into its own container later is a much smaller change than splitting a tangled monolith.
