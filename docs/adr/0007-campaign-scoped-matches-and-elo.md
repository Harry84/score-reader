---
status: accepted
---

# campaign_id as an opaque reference, and per-campaign ELO scoping

Turn already exists as an opaque external reference this project stores but never models the lifecycle of (ADR/CONTEXT.md). Extending that: the NPC Commander project may run multiple separate, time-boxed campaigns (whole runs of the war) that should be kept distinct rather than blurred into one endless history. If campaign boundaries aren't represented here, a `turn_id` value could in principle repeat across two different campaigns, and `(turn_id, system_id)` — the only thing currently disambiguating a Match's place in history — would incorrectly conflate matches from unrelated campaigns.

We're adding `campaign_id` to `matches` and `pending_matches`, treated exactly like `turn_id`: a required, opaque reference supplied by the campaign project, with no local campaign lifecycle or schema of our own. Team/Player identity (the reference DB) and the System map stay campaign-agnostic — a roster and the physical 8-system map both persist across campaigns, only the war-in-progress state (Turns, Matches) is campaign-scoped.

ELO is scoped per campaign: `recompute_team_elo` replays only the current campaign's matches, and `team_elo_ratings`/`team_elo_history` are keyed by `(team_id, campaign_id)` rather than `team_id` alone. A team's rating resets to the starting ELO at the beginning of each new campaign rather than carrying forward — matching the "separate events we want to keep" framing rather than treating campaigns as mere labels on one continuous ladder.

**Consequences:** every ingestion entry point (`start_ingestion`, the `POST /matches` route) now requires `campaign_id` alongside `turn_id`/`system_id`/`match_type`. Historical data migrated from the old SQLite system (ADR-0003) predates the campaign concept entirely and has no meaningful campaign_id — it stays out of scope for campaign-scoped ELO grouping, consistent with it already being excluded from `match_type = 'team'`-based team ELO wherever match_type differs.
