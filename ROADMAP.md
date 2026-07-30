# Roadmap: Discord-driven backend

Implementation plan for turning this project into the score/stats/ELO backend for the Discord campaign game. See `CONTEXT.md` for vocabulary and `docs/adr/` for the decisions this plan assumes. Each phase ends with tests before moving on, per the grilling session's agreement to build and verify incrementally.

## Phase 0 — Foundations

- Add a dedicated Postgres container (ADR-0006) to `docker-compose.yml`.
- Port the existing SQLite schema (`seasons`, `teams`, `matches`, `players`, `player_stats`, `ref_teams`, `ref_players`) to Postgres, adding: `turn_id` and `system_id` on `matches`; a small hand-seeded `systems` lookup table (the 8 named systems, incl. The Maw); a `pending_matches` table for the ingestion workflow (ADR-0005).
- One-time migration script importing existing `squadrons_stats.db` / `squadrons_reference.db` data into Postgres (agreed: history carries forward, old CLI/SQLite flow is retired once this lands).
- Shared-secret auth middleware for any endpoint the campaign project calls, and for outbound webhook calls (agreed: static API key both directions).

**Tests:** migration script produces matching row counts and spot-checked known matches/ELO values against the old SQLite data; `pending_matches` schema round-trips a hand-built fixture through every status value.

## Phase 1 — Ingestion workflow (backend core)

- Bring `score_extractor`'s Claude-vision extraction in as a module/route on the backend API.
- Implement the `pending_matches` state machine end to end: `extracted → awaiting_match_type → awaiting_player_match:<player> → awaiting_subbing:<player> → awaiting_role:<player> → ready → persisted`, porting the suggestion logic (fuzzy match candidates, subbing inference, role defaults) from `reference_manager.py` / `stats_db_processor_direct.py`.
- `POST /matches` (turn_id, system_id, image) → creates the row, returns first question or completes.
- `POST /matches/{id}/answer` → applies an answer, advances, returns next question or completes.
- On reaching `ready`: persist Match + player_stats, recompute stats/ELO synchronously (agreed default), reusing `elo_ladder.py`/`player_elo_ladder.py`/`role_elo_calculator.py` logic against Postgres.

**Tests:** unit tests per state transition (given a known-ambiguous name, correct candidates are returned; given an answer, correct next state); one full happy-path integration test (unambiguous screenshot → persisted Match + updated ELO in one call); one deliberately-ambiguous fixture that pauses at the expected step and resumes correctly on answer.

## Phase 2 — Read API and push notification

- Read endpoints the campaign project needs: latest Match for `(turn_id, system_id)`, Team roster, player/team stats and ELO ladder.
- Webhook client: once a Match reaches `persisted`, POST a summary to the campaign project's configured webhook URL (shared secret auth, per ADR-0001).

**Tests:** contract tests for each read endpoint against seeded fixtures; webhook call tested against a mock receiver, asserting payload shape and behavior on failure/timeout.

## Phase 3 — Score bot

- New bot process/container (ADR-0001), scoped to the two faction channels.
- Team-admin commands (create team, add/remove player) calling the backend API — a thin Discord-native wrapper over `reference_manager` functionality.
- Screenshot listener: detect an image attachment, `POST /matches`, render whatever question comes back as Discord UI (buttons/reactions/reply) if the workflow pauses (ADR-0002), relay the human's answer to `POST /matches/{id}/answer`, react ✅ on `persisted` / ❌ with the error on failure.

**Tests:** bot logic unit-tested against a mocked backend API (question-rendering, answer-relaying); manual end-to-end test posting a real screenshot into a test Discord server.

## Phase 4 — Compose and deployment

- `docker-compose.yml` wiring Postgres + backend + score bot; host-mapped ports and env-var base URLs for cross-repo calls (agreed: no shared Docker network across repos).
- Decide the fate of the GitHub Pages static-site export in light of retiring the old CLI flow — likely a scheduled job that calls the new read API to regenerate the same JSON reports, rather than reading SQLite directly.

**Tests:** compose smoke test — all containers healthy, backend reachable, migrations applied on a clean volume.

## Phase 5 — Campaign integration validation

- End-to-end test against a stub (or the real thing, if ready) of the campaign project's webhook receiver, confirming the push-notification contract.
- Validate the seeded `systems` lookup against the campaign doc's 8 systems (Nadiri Dockyards, Esseles, Zavian Abyss, Galitan, Sissubo, Yavin Prime, the resolved 8th/Fostar Haven question, The Maw).

## Open items carried from the campaign project, relevant to us

- Whether the 8th cube node stays Fostar Haven or is replaced — affects the seeded `systems` table (Phase 0), not this project's logic.
- Resolved: this project's scope is screenshot-only. Procedurally-resolved mismatches (no game played) are the campaign project's own bookkeeping and never become a Match here — `POST /matches` always requires an image, no non-screenshot entry point needed.
