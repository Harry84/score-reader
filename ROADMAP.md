# Roadmap: Discord-driven backend

Implementation plan for turning this project into the score/stats/ELO backend for the Discord campaign game. See `CONTEXT.md` for vocabulary and `docs/adr/` for the decisions this plan assumes. Each phase ends with tests before moving on, per the grilling session's agreement to build and verify incrementally.

## Status as of 2026-07-31

**Done: Phases 0, 1, 2.** All on branch `feature/containerise`, one commit per vertical slice. 43 new tests passing (`tests/db`, `tests/ingestion`, `tests/api`, `tests/stats`, `tests/teams`) plus the pre-existing suite (see note below). Real dev Postgres (`docker compose up postgres`, port 5433) has the real migrated historical data (5 seasons, 17 matches) and is on the latest migration (`0010_team_captain.sql`).

Along the way, two things were added beyond the original phase write-ups (both now folded into the descriptions below and worth reading if picking this back up cold):
- **`campaign_id`** (ADR-0007) — an opaque reference on `matches`/`pending_matches`, mirroring `turn_id`, plus per-campaign ELO scoping. Added after Phase 1 shipped, in response to realizing separate time-boxed campaigns needed to stay isolated.
- **Player/role ELO** (`stats/player_elo.py`) — pickup/ranked matches were persisting correctly but computing zero ELO until this was added; team ELO alone wasn't the full picture.
- **Captain/Admin authorization** (ADR-0008) — Phase 2 turned out to need more than plain CRUD once "only a team's captain can touch its own roster, only admins can create new teams/players" came up.

**Not started: Phases 3–6.** Next up is Phase 3 (read API + push notification) — see that section below for the concrete shape.

**Small known loose ends, not blocking:**
- The `pending_matches.status` CHECK constraint still permits a `'ready'` value from the original ADR-0005 sketch that no code path ever actually sets (matches got dropped: `awaiting_match_type`, `awaiting_subbing` — same story). Harmless, just a little stale; worth tidying whenever that constraint is next touched.
- Three pre-existing test files were already broken before this work started and remain untouched: `tests/test_stats_reader.py` (imports a `stats_db_processor` module a prior commit deleted — fails to even collect), `tests/test_score_extractor.py`, and `stats_reader/test_elo_ladder.py` (unrelated pre-existing failures). Confirmed via `git status`/`git log` at the time not to be something this work caused.
- Phase 5's role-reporting port (`generate_player_roles_json.py`/`generate_role_reports.py`) is a known gap, already itemized in that phase below.

## Phase 0 — Foundations ✅ done

- Add a dedicated Postgres container (ADR-0006) to `docker-compose.yml`.
- Port the existing SQLite schema (`seasons`, `teams`, `matches`, `players`, `player_stats`, `ref_teams`, `ref_players`) to Postgres, adding: `turn_id` and `system_id` on `matches`; a small hand-seeded `systems` lookup table (the 8 named systems, incl. The Maw); a `pending_matches` table for the ingestion workflow (ADR-0005).
- One-time migration script importing existing `squadrons_stats.db` / `squadrons_reference.db` data into Postgres (agreed: history carries forward, old CLI/SQLite flow is retired once this lands).
- Shared-secret auth middleware for any endpoint the campaign project calls, and for outbound webhook calls (agreed: static API key both directions).

**Tests:** migration script produces matching row counts and spot-checked known matches/ELO values against the old SQLite data; `pending_matches` schema round-trips a hand-built fixture through every status value.

## Phase 1 — Ingestion workflow (backend core) ✅ done

- Backend API runs on FastAPI (new dependency; not Azure Functions — that binding stays specific to the existing `score_extractor` Function and isn't reused here, since a plain-container FastAPI app fits ADR-0004's coarse-grained, docker-compose-native shape better).
- Bring `score_extractor`'s Claude-vision extraction in as a module/route on the backend API, but keep it behind a seam: the ingestion workflow core operates on already-extracted JSON, decoupled from the real vision call (mocked in tests, same pattern the existing `test_score_extractor.py` already uses).
- Implement the `pending_matches` state machine. Actual sequence that shipped: `extracted → [awaiting_player_match:<player> | awaiting_team_assignment:<faction> | awaiting_role:<player>]* → persisted` — each `awaiting_*` step optional and only hit on genuine ambiguity, resolved via `submit_answer` and re-advanced. (The original sketch's `awaiting_match_type` and `awaiting_subbing` states were dropped during implementation — see the loose-ends note above.) Ported the suggestion logic (fuzzy match candidates, subbing inference, role defaults) from `reference_manager.py` / `stats_db_processor_direct.py`. `turn_id`, `system_id`, `campaign_id`, and `match_type` are required inputs at ingestion start, not ambiguous steps — the score bot always knows these from context (which command/channel triggered it), and match_type in particular (team/pickup/ranked) is the campaign project's call to make if it ever needs disambiguating, not something this project's data can infer.
- `POST /matches` (turn_id, system_id, match_type, image) → creates the `pending_matches` row, returns first question or completes.
- `POST /matches/{id}/answer` → applies an answer, advances, returns next question or completes.
- Once every ambiguity resolves: persist Match + player_stats, recompute stats/ELO synchronously (agreed default). `stats/team_elo.py` ports `elo_ladder.py`'s team ELO for `match_type = "team"`; `stats/player_elo.py` ports `player_elo_ladder.py` (general ladder) and `role_elo_calculator.py` (Flex/Support/Farmer ladders, combined into one pass rather than the original's two separate recomputations) for `match_type` pickup/ranked. Both are scoped per `(campaign_id, match_type)` per ADR-0007 — no continuous cross-campaign ladder. `generate_player_roles_json.py`/`generate_role_reports.py` were confirmed to be pure reporting artifacts over `player_stats.role` (not ELO prerequisites) and don't need porting for ELO to work; they'd only matter again if/when a downstream report export is rebuilt (Phase 5).

**Tests:** first vertical slice is the fully-unambiguous happy path (every player exactly matches an existing `ref_players` row, primary teams cleanly account for both rosters) going straight from `extracted` to `persisted` with no pause at all. Then one slice per ambiguity type (unrecognized player name, uncertain team assignment, uncertain role), each confirming the workflow pauses at the right step with the right candidates and resumes correctly on answer. HTTP-layer tests (via FastAPI's `TestClient`) come after the workflow core is solid. ELO tests use independently hand-computed expected values (a standalone script applying the public ELO formula), not values derived by importing the implementation.

## Phase 2 — Team onboarding API ✅ done

- Endpoints backing the score bot's team-admin commands (Phase 4), reusing the reference DB rather than a new roster concept (CONTEXT.md: Team). Two trust levels, per ADR-0008:
  - Admin-only (trusted implicitly from the bot, no independent backend check): `POST /teams` (create/find by name), `POST /players` (create a genuinely new canonical player), `POST /teams/{id}/captain` (assign/change `captain_discord_id`).
  - Captain-only (backend-verified against `ref_teams.captain_discord_id`): `POST /teams/{id}/roster` — attach an *existing* `ref_player_id` to that team, rejected if the caller's `requesting_discord_id` isn't the team's captain.
  - Open lookups: `GET /teams`, `GET /teams/{id}` for the bot to render pickers/rosters.
- This has to land before real Discord usage of Phase 1 is possible — ingestion's identity resolution depends on rosters already existing in `ref_teams`/`ref_players` — but is being built after the ingestion core so the workflow's assumptions about what "resolved" reference data looks like are already settled by real tests, not guessed at.

**Tests:** integration tests hitting each endpoint against a real Postgres test database — create-team idempotency (matching `reference_manager.add_team`'s existing behavior of returning the existing row on a duplicate name), roster-attach happy path as the correct captain, roster-attach rejected for a non-captain caller, attach-to-nonexistent-team error case.

## Phase 3 — Read API and push notification — not started, next up

- Read endpoints the campaign project needs: latest Match for `(turn_id, system_id)`, Team roster, player/team stats and ELO ladder.
- Webhook client: once a Match reaches `persisted`, POST a summary to the campaign project's configured webhook URL (shared secret auth, per ADR-0001).

**Tests:** contract tests for each read endpoint against seeded fixtures; webhook call tested against a mock receiver, asserting payload shape and behavior on failure/timeout.

## Phase 4 — Score bot — not started

- New bot process/container (ADR-0001), scoped to the two faction channels.
- Team-admin commands (create team, add/remove player) calling the Phase 2 API — a thin Discord-native wrapper, not new logic.
- Screenshot listener: detect an image attachment, `POST /matches`, render whatever question comes back as Discord UI (buttons/reactions/reply) if the workflow pauses (ADR-0002), relay the human's answer to `POST /matches/{id}/answer`, react ✅ on `persisted` / ❌ with the error on failure.

**Tests:** bot logic unit-tested against a mocked backend API (question-rendering, answer-relaying); manual end-to-end test posting a real screenshot into a test Discord server.

## Phase 5 — Compose and deployment — not started

- `docker-compose.yml` wiring Postgres + backend + score bot; host-mapped ports and env-var base URLs for cross-repo calls (agreed: no shared Docker network across repos).
- Decide the fate of the GitHub Pages static-site export in light of retiring the old CLI flow — likely a scheduled job that calls the new read API to regenerate the same JSON reports, rather than reading SQLite directly.
- Known gap to close here: `generate_player_roles_json.py` (player→role lookup for labeling leaderboard rows) and `generate_role_reports.py` (`player_performance_role_*.json` — kills/deaths/score aggregates by role and match type) were never ELO prerequisites (Phase 1), but they're still real reporting outputs the old web viz depended on and nothing in the new system produces yet. Needs porting to Postgres queries against `player_stats`/`ref_players`, exposed through the read API (Phase 3) rather than written as files directly.

**Tests:** compose smoke test — all containers healthy, backend reachable, migrations applied on a clean volume. Role-report queries get their own tests against seeded fixtures (expected aggregates hand-computed, not re-derived from the query itself).

## Phase 6 — Campaign integration validation — not started

- End-to-end test against a stub (or the real thing, if ready) of the campaign project's webhook receiver, confirming the push-notification contract.
- Validate the seeded `systems` lookup against the campaign doc's 8 systems (Nadiri Dockyards, Esseles, Zavian Abyss, Galitan, Sissubo, Yavin Prime, the resolved 8th/Fostar Haven question, The Maw).

## Open items carried from the campaign project, relevant to us

- Whether the 8th cube node stays Fostar Haven or is replaced — affects the seeded `systems` table (Phase 0), not this project's logic.
- Resolved: this project's scope is screenshot-only. Procedurally-resolved mismatches (no game played) are the campaign project's own bookkeeping and never become a Match here — `POST /matches` always requires an image, no non-screenshot entry point needed.
