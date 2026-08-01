# Roadmap: Discord-driven backend

Implementation plan for turning this project into the score/stats/ELO backend for the Discord campaign game. See `CONTEXT.md` for vocabulary and `docs/adr/` for the decisions this plan assumes. Each phase ends with tests before moving on, per the grilling session's agreement to build and verify incrementally.

## Handover — start here next session

**Phase 3 (score bot MVP) is functionally complete.** A real bot (`bot/`) runs against the backend, and the screenshot → persisted Match loop has been proven live in a real Discord test server (`#ai-test`) — not just in automated tests. Team onboarding commands (`!create-team`, `!set-captain`, `!add-roster`) work end-to-end too.

**Live-ambiguity testing, in progress:** `awaiting_player_match` has now been triggered live and fully round-tripped - the dead-end case (no fuzzy candidates), the pick-a-candidate-and-persist case, and the new "0 = none of the above" rejection case (see below) all confirmed working in `#ai-test`. Still not yet triggered live: `awaiting_team_assignment`, `awaiting_roster_size`, `awaiting_missing_field`. All four have full automated test coverage regardless.

Three real bugs were found and fixed by that live testing (the automated suite hadn't caught any of them):
- **Stuck conversation state on a dead-end `awaiting_player_match`.** A zero-candidate pause was still registered as an answerable pending question, so any next message in the channel (including an unrelated new screenshot) got swallowed into `parse_answer`/`_parse_index` and produced a nonsensical "Reply with a number between 1 and 0" - forever, until the bot process was restarted. Fixed via `conversation.is_dead_end()`: `bot/main.py` no longer registers a pending question for a candidate-less pause.
- **Resolved player identity not actually persisted.** When a `player_match` ambiguity was resolved via picking a candidate (as opposed to an exact-name match), `ingestion/workflow.py`'s `_resolve_faction` kept the raw as-typed/extracted name (e.g. a screenshot's "Side Stac") in `player_stats.player_name` instead of switching to the resolved `ref_players` canonical name ("NiWi-Side_Stack"). Cosmetic in the match summary, but also broke `!edit <match> <player> ...` - which looks up by exact `player_name` - for anyone typing the correct name instead of the typo. Fixed: `_resolve_faction` now overwrites `"player"` with the canonical `ref_player["name"]` once resolved.
- **Discord silently renumbers `N.` list lines.** `render_question`'s numbered candidate list (`1. Wedge`, `2. Wedgy`, ...) gets rendered by Discord's client as a native ordered list, which renumbers sequentially from the first item *regardless of the actual digit in the source text* - so a `0. None of the above` line placed after `3.` displayed as `4.`, not `0.`, and typing the number Discord actually showed didn't match what the bot's parser expected. Fixed by backslash-escaping the periods (`1\. Wedge`) to force literal rendering instead of Discord's list markdown.

**Beyond Phase 3's original scope, added this session:**
- **"None of the above" option on `player_match`/`team_assignment` questions.** A fuzzy-matched candidate that merely looks similar (not a genuine typo of that person) can now be explicitly rejected by replying `0`, rather than being forced into picking a wrong candidate. Renders via `conversation.render_rejection()`, telling the user to ask an admin to add the genuinely-new player instead.
- **Screenshot ingestion gated behind an admin reaction.** Previously any message with an attachment in the bot channel triggered ingestion immediately - now `bot/main.py` acks the post and adds a 📥 reaction, but only actually calls `_handle_screenshot` once a Discord user holding the `BOT_ADMIN_ROLE_NAME` role (default `"Bot Admin"`, `bot/config.py`) reacts with 📥 themselves (`on_raw_reaction_add`). ✅ marks the resulting screenshot message once the match is actually persisted, per ADR-0001's original "reacts on the source message to acknowledge ingestion" intent. Confirmed via discord.py docs research that this works via `on_raw_reaction_add`'s `payload.member` without needing the privileged Server Members Intent - **not yet verified live**, do that before calling this closed out. Deliberately scoped to screenshot ingestion only: `!create-team`/`!set-captain`/`!add-roster` remain un-gated even though ADR-0008 describes them as intended to be Discord-role-checked - a known, pre-existing gap, left as an explicit follow-up rather than folded into this change.

**Next up:** live-verify the admin-reaction gate and the three remaining `awaiting_*` pause types, then either wire the same admin-role check into the team-onboarding commands (the flagged gap above) or move on to the rest of Phase 4 (buttons/select-menus for `awaiting_*` rendering, slash commands, faction-channel scoping). Per the original plan, the alternative is to switch over to the *campaign project* repo for a while before coming back here.

**Environment notes for picking this up cold:**
- Backend runs locally via `python -m uvicorn api.main:app --port 8001` against the dev Postgres (`docker compose up -d postgres`, port 5433). The bot runs via `python -m bot.main`, reading `DISCORD_BOT_TOKEN`/`BACKEND_URL`/`BOT_CHANNEL_NAME`/`BOT_ADMIN_ROLE_NAME` etc. from `.env` (see `bot/config.py`). Neither process auto-reloads on code changes — restart both after editing. Testing the new admin-reaction gate requires a Discord role named "Bot Admin" (or `BOT_ADMIN_ROLE_NAME` in `.env` pointed at an existing role) assigned to whichever account will react to approve ingestion.
- Manual bot testing happens against the **real** dev Postgres (not a scratch DB), isolated by using `campaign_id="test-campaign"` (the bot's default) since ELO recompute is scoped per `(campaign_id, match_type)` per ADR-0007. Clean up test rows (`matches`, `player_stats`, `player_elo_*`, `team_elo_*`, `pending_matches`) filtered by that `campaign_id` after each session — confirmed safe/isolated from the real 17-match history by direct inspection.

## Status as of 2026-08-01

**Done: Phases 0, 1, 2, 3.** All on branch `feature/containerise`, one commit per vertical slice, pushed to `origin/feature/containerise`. 104 tests passing across `tests/db`, `tests/ingestion`, `tests/api`, `tests/stats`, `tests/teams`, `tests/bot`, plus the pre-existing suite (see note below). Real dev Postgres (`docker compose up postgres`, port 5433) has the real migrated historical data (5 seasons, 17 matches) and is on the latest migration (`0011_pending_matches_status_validation.sql`).

Along the way, several things were added beyond the original phase write-ups (folded into the descriptions below, worth knowing about if picking this up cold):
- **`campaign_id`** (ADR-0007) — an opaque reference on `matches`/`pending_matches`, mirroring `turn_id`, plus per-campaign ELO scoping. Added after Phase 1 shipped, in response to realizing separate time-boxed campaigns needed to stay isolated.
- **Player/role ELO** (`stats/player_elo.py`) — pickup/ranked matches were persisting correctly but computing zero ELO until this was added; team ELO alone wasn't the full picture.
- **Captain/Admin authorization** (ADR-0008) — Phase 2 turned out to need more than plain CRUD once "only a team's captain can touch its own roster, only admins can create new teams/players" came up.
- **`GET /players?name=`** — a lookup gap identified while building Phase 3, needed so the bot can resolve a typed player name into a `ref_player_id` before calling `POST /teams/{id}/roster`.
- **Post-persist match editing** (`PATCH /matches/{id}/players/{name}`, `PATCH /matches/{id}/winner`; bot `!edit`/`!edit-winner`/`!help`) — not part of Phase 3's original scope. Added after live-testing surfaced that a persisted match with no way to fix an extraction mistake wasn't good enough. Mirrors `stats_reader/data_cleaner.py`'s old pre-DB CLI review step (which covered the same fields: match result, player name, role, score, kills, deaths, assists, AI kills, cap ship damage), now applied after a match is already in Postgres rather than before it hits a JSON file. Safe because `recompute_player_elo`/`recompute_team_elo` always replay their full `(campaign_id, match_type)` history from scratch — editing and re-running them has no incremental state to get wrong.
- **`awaiting_role` ambiguity removed** — a missing `primary_role` used to pause the whole match pending clarification. It no longer does: role only affects which role-ELO ladder a player lands on, not who played or who won, so it's not worth blocking persist over. A match now persists with `player_stats.role = NULL` for that player (a legitimate "no role this match" state — e.g. a genuine multi-role game), fixable via `!edit <match> <player> role=<Farmer|Flex|Support|none>` whenever someone notices. `awaiting_player_match` and `awaiting_team_assignment` were deliberately kept as pre-persist pauses — those decide *who* played and *which team* gets credited, where a bad auto-guess is much more likely to sit unnoticed than a wrong role would.
- **Two new pre-resolution validation pauses** — `awaiting_roster_size:<faction>` (fires when a faction doesn't have exactly `EXPECTED_ROSTER_SIZE` (5) players; confirm to proceed anyway, e.g. a genuine no-show) and `awaiting_missing_field:<player>:<field>` (fires when a player record is missing a required stat field or `position`; answer supplies the value). Both run before any player identity/team resolution - no point resolving identities against data already known to be incomplete. Requested explicitly, and deliberately kept as pauses (not defaults+edit-after-the-fact like role) since a bad guess at "which 5 players actually played" is a correctness problem, not just a categorization one.

**Not started: Phases 4–7.**

**Small known loose ends, not blocking:**
- The `pending_matches.status` CHECK constraint still permits `'ready'` and `awaiting_match_type`/`awaiting_subbing`, none of which any code path ever actually sets (dropped from the original ADR-0005 sketch during Phase 1). `awaiting_role:%` was tidied out this session (migration `0011`) since it's now genuinely gone from the code too; the remaining three are harmless, just stale.
- Three pre-existing test files were already broken before this work started and remain untouched: `tests/test_stats_reader.py` (imports a `stats_db_processor` module a prior commit deleted — fails to even collect), `tests/test_score_extractor.py`, and `stats_reader/test_elo_ladder.py` (unrelated pre-existing failures). Confirmed via `git status`/`git log` at the time not to be something this work caused.
- Phase 6's role-reporting port (`generate_player_roles_json.py`/`generate_role_reports.py`) is a known gap, already itemized in that phase below.
- `score_extractor`'s Claude model ID was found stale (`claude-3-7-sonnet-20250219`, retired) during Phase 3 live-testing and bumped to `claude-sonnet-5` — worth a periodic sanity check that this hasn't drifted again.

## Phase 0 — Foundations ✅ done

- Add a dedicated Postgres container (ADR-0006) to `docker-compose.yml`.
- Port the existing SQLite schema (`seasons`, `teams`, `matches`, `players`, `player_stats`, `ref_teams`, `ref_players`) to Postgres, adding: `turn_id` and `system_id` on `matches`; a small hand-seeded `systems` lookup table (the 8 named systems, incl. The Maw); a `pending_matches` table for the ingestion workflow (ADR-0005).
- One-time migration script importing existing `squadrons_stats.db` / `squadrons_reference.db` data into Postgres (agreed: history carries forward, old CLI/SQLite flow is retired once this lands).
- Shared-secret auth middleware for any endpoint the campaign project calls, and for outbound webhook calls (agreed: static API key both directions).

**Tests:** migration script produces matching row counts and spot-checked known matches/ELO values against the old SQLite data; `pending_matches` schema round-trips a hand-built fixture through every status value.

## Phase 1 — Ingestion workflow (backend core) ✅ done

- Backend API runs on FastAPI (new dependency; not Azure Functions — that binding stays specific to the existing `score_extractor` Function and isn't reused here, since a plain-container FastAPI app fits ADR-0004's coarse-grained, docker-compose-native shape better).
- Bring `score_extractor`'s Claude-vision extraction in as a module/route on the backend API, but keep it behind a seam: the ingestion workflow core operates on already-extracted JSON, decoupled from the real vision call (mocked in tests, same pattern the existing `test_score_extractor.py` already uses).
- Implement the `pending_matches` state machine. Sequence that shipped: `extracted → [awaiting_player_match:<player> | awaiting_team_assignment:<faction>]* → persisted` — each `awaiting_*` step optional and only hit on genuine ambiguity, resolved via `submit_answer` and re-advanced. (The original sketch's `awaiting_match_type` and `awaiting_subbing` states were dropped during implementation — see the loose-ends note above. A third state, `awaiting_role:<player>`, did ship as part of this phase but was removed in Phase 3 once post-persist editing existed to fix a missing role after the fact — see the Phase 3 status notes. Two more states, `awaiting_roster_size:<faction>` and `awaiting_missing_field:<player>:<field>`, were added in Phase 3 to validate the raw extraction before any of this identity/team resolution runs at all - see Phase 3 below.) Ported the suggestion logic (fuzzy match candidates, subbing inference, role defaults) from `reference_manager.py` / `stats_db_processor_direct.py`. `turn_id`, `system_id`, `campaign_id`, and `match_type` are required inputs at ingestion start, not ambiguous steps — the score bot always knows these from context (which command/channel triggered it), and match_type in particular (team/pickup/ranked) is the campaign project's call to make if it ever needs disambiguating, not something this project's data can infer.
- `POST /matches` (turn_id, system_id, match_type, image) → creates the `pending_matches` row, returns first question or completes.
- `POST /matches/{id}/answer` → applies an answer, advances, returns next question or completes.
- Once every ambiguity resolves: persist Match + player_stats, recompute stats/ELO synchronously (agreed default). `stats/team_elo.py` ports `elo_ladder.py`'s team ELO for `match_type = "team"`; `stats/player_elo.py` ports `player_elo_ladder.py` (general ladder) and `role_elo_calculator.py` (Flex/Support/Farmer ladders, combined into one pass rather than the original's two separate recomputations) for `match_type` pickup/ranked. Both are scoped per `(campaign_id, match_type)` per ADR-0007 — no continuous cross-campaign ladder. `generate_player_roles_json.py`/`generate_role_reports.py` were confirmed to be pure reporting artifacts over `player_stats.role` (not ELO prerequisites) and don't need porting for ELO to work; they'd only matter again if/when a downstream report export is rebuilt (Phase 6).

**Tests:** first vertical slice is the fully-unambiguous happy path (every player exactly matches an existing `ref_players` row, primary teams cleanly account for both rosters) going straight from `extracted` to `persisted` with no pause at all. Then one slice per ambiguity type (unrecognized player name, uncertain team assignment - originally also uncertain role, superseded by Phase 3's edit-based approach), each confirming the workflow pauses at the right step with the right candidates and resumes correctly on answer. HTTP-layer tests (via FastAPI's `TestClient`) come after the workflow core is solid. ELO tests use independently hand-computed expected values (a standalone script applying the public ELO formula), not values derived by importing the implementation.

## Phase 2 — Team onboarding API ✅ done

- Endpoints backing the score bot's team-admin commands (Phase 3/4), reusing the reference DB rather than a new roster concept (CONTEXT.md: Team). Two trust levels, per ADR-0008:
  - Admin-only (trusted implicitly from the bot, no independent backend check): `POST /teams` (create/find by name), `POST /players` (create a genuinely new canonical player), `POST /teams/{id}/captain` (assign/change `captain_discord_id`).
  - Captain-only (backend-verified against `ref_teams.captain_discord_id`): `POST /teams/{id}/roster` — attach an *existing* `ref_player_id` to that team, rejected if the caller's `requesting_discord_id` isn't the team's captain.
  - Open lookups: `GET /teams`, `GET /teams/{id}` for the bot to render pickers/rosters.
- This has to land before real Discord usage of Phase 1 is possible — ingestion's identity resolution depends on rosters already existing in `ref_teams`/`ref_players` — but is being built after the ingestion core so the workflow's assumptions about what "resolved" reference data looks like are already settled by real tests, not guessed at.

**Tests:** integration tests hitting each endpoint against a real Postgres test database — create-team idempotency (matching `reference_manager.add_team`'s existing behavior of returning the existing row on a duplicate name), roster-attach happy path as the correct captain, roster-attach rejected for a non-captain caller, attach-to-nonexistent-team error case.

## Phase 3 — Minimal score bot (MVP) ✅ done (one live-test gap remains — see handover notes)

Deliberately cut down to the smallest thing that proves the real Discord loop works, before investing in polish (that's Phase 4). Reuses Phases 1–2's APIs only — no dependency on Phase 5 (read API/webhook).

- New bot process (ADR-0001; `bot/` in this repo, `discord.py`), a Discord application set up manually (token + server invite + Message Content intent), listening only in `#ai-test` (`bot/config.py: BOT_CHANNEL_NAME`).
- Added the missing `GET /players?name=` lookup endpoint (backend gap identified this session) so the bot can resolve a typed player name to a `ref_player_id` before calling `POST /teams/{id}/roster`.
- Minimal plain-text commands (no slash commands): `!create-team`, `!set-captain`, `!add-roster`, plus `!help` listing all commands.
- Screenshot flow: detect an image attachment, call `POST /matches` with it (`campaign_id`/`turn_id`/`system_id`/`match_type` hardcoded via `bot/config.py` env vars for now, per the original plan to keep this crude), and if the response pauses, relay the question as plain text and feed the next message's content back as the answer to `POST /matches/{id}/answer`. Buttons/reactions/nicer rendering (ADR-0002's actual intent) are still Phase 4.
- Success signal: a formatted table (`bot/conversation.py: render_match_summary`) showing the persisted match's winner and every player's score/kills/deaths/assists/AI kills/cap ship damage — upgraded from a bare match-ID reply once live-testing showed a plain ID wasn't enough to sanity-check the extraction.
- **Beyond the original scope:** post-persist editing (`!edit <match> <player> <field>=<value>...`, `!edit-winner <match> <IMPERIAL|REBEL>`) — see the Status notes above for why, and the `awaiting_role` ambiguity removal this enabled.
- **Also beyond the original scope:** two extraction-validation pauses requested mid-session - `awaiting_roster_size:<faction>` (a faction without exactly 5 players; reply `confirm` to proceed anyway) and `awaiting_missing_field:<player>:<field>` (a player missing a required stat/position; reply with the value). Both run in `_advance` before any player identity/team resolution. Needed a new migration (`0011_pending_matches_status_validation.sql`) to widen the `pending_matches.status` CHECK constraint, applied to the real dev DB.

**Tests:** 89 tests across `tests/bot` (pure logic - question/answer/edit-command parsing, help/summary rendering, backend HTTP client wrapper against a mocked transport) and the backend changes in `tests/ingestion`/`tests/api`, including the two new validation pauses and a full 5-a-side happy-path regression test. The real proof for the unambiguous path is manual: a real screenshot posted in `#ai-test` round-tripped to a persisted Match, and `!edit`/`!edit-winner` were exercised live against real persisted matches too. **Not yet done live, for any of the four `awaiting_*` pause types** (`awaiting_player_match`, `awaiting_team_assignment`, `awaiting_roster_size`, `awaiting_missing_field`): deliberately triggering one through the actual bot and watching the pause-then-answer conversation happen in Discord. Automated coverage exists for all four, but every live Discord test so far happened to hit the unambiguous, fully-populated 5-a-side path.

## Phase 4 — Score bot polish — not started

- Round out Phase 3's cut corners: reactions (✅ on `persisted` / ❌ with the error on failure) instead of plain text acks, buttons/select-menus for rendering `awaiting_*` questions instead of plain-text back-and-forth (the actual ADR-0002 intent), slash commands. (A plain-text `!help` already exists from Phase 3 - this is about the richer slash-command version with per-argument validation, not adding help from scratch.)
- Scope roster/screenshot commands to the two faction channels properly (ADR-0001) - Phase 3 only listens on a single test channel (`#ai-test`).

**Tests:** same bot-logic unit tests extended for the richer rendering; manual re-test in Discord.

## Phase 5 — Read API and push notification — not started

- Read endpoints the campaign project needs: latest Match for `(turn_id, system_id)`, Team roster, player/team stats and ELO ladder.
- Webhook client: once a Match reaches `persisted`, POST a summary to the campaign project's configured webhook URL (shared secret auth, per ADR-0001).
- Deferred behind the score bot phases because nothing here is needed to prove the core ingestion loop works, and the campaign project isn't ready to receive the webhook yet regardless.

**Tests:** contract tests for each read endpoint against seeded fixtures; webhook call tested against a mock receiver, asserting payload shape and behavior on failure/timeout.

## Phase 6 — Compose and deployment — not started

- `docker-compose.yml` wiring Postgres + backend + score bot; host-mapped ports and env-var base URLs for cross-repo calls (agreed: no shared Docker network across repos).
- Decide the fate of the GitHub Pages static-site export in light of retiring the old CLI flow — likely a scheduled job that calls the new read API to regenerate the same JSON reports, rather than reading SQLite directly.
- Known gap to close here: `generate_player_roles_json.py` (player→role lookup for labeling leaderboard rows) and `generate_role_reports.py` (`player_performance_role_*.json` — kills/deaths/score aggregates by role and match type) were never ELO prerequisites (Phase 1), but they're still real reporting outputs the old web viz depended on and nothing in the new system produces yet. Needs porting to Postgres queries against `player_stats`/`ref_players`, exposed through the read API (Phase 5) rather than written as files directly.

**Tests:** compose smoke test — all containers healthy, backend reachable, migrations applied on a clean volume. Role-report queries get their own tests against seeded fixtures (expected aggregates hand-computed, not re-derived from the query itself).

## Phase 7 — Campaign integration validation — not started

- End-to-end test against a stub (or the real thing, if ready) of the campaign project's webhook receiver, confirming the push-notification contract.
- Validate the seeded `systems` lookup against the campaign doc's 8 systems (Nadiri Dockyards, Esseles, Zavian Abyss, Galitan, Sissubo, Yavin Prime, the resolved 8th/Fostar Haven question, The Maw).

## Open items carried from the campaign project, relevant to us

- Whether the 8th cube node stays Fostar Haven or is replaced — affects the seeded `systems` table (Phase 0), not this project's logic.
- Resolved: this project's scope is screenshot-only. Procedurally-resolved mismatches (no game played) are the campaign project's own bookkeeping and never become a Match here — `POST /matches` always requires an image, no non-screenshot entry point needed.
