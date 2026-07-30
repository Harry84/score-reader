---
status: accepted
---

# Two different trust levels for team onboarding: backend-verified Captain, bot-asserted Admin

Phase 2's team onboarding needs an authorization model, not just CRUD: a Captain should only be able to attach existing canonical Players to the one Team they captain, while creating a genuinely new Team or Player is Admin-only. We deliberately gave these two roles different trust levels rather than treating them uniformly.

Captain-of-team is backend-verified: `ref_teams.captain_discord_id` is reference data the backend owns outright, so `POST /teams/{id}/roster` independently checks the calling Discord user against it rather than trusting whatever the score bot asserts — defense in depth for the one action a compromised or buggy bot command could otherwise use to move players onto the wrong roster. Admin-ness, by contrast, is not modeled in this project's schema at all: it lives in Discord's own role system (e.g. a "Bot Admin" server role) and is checked entirely by the score bot before it ever calls the backend's team/player-creation endpoints, consistent with the existing trust boundary where the backend already takes the bot's word for `turn_id`/`match_type`/etc. (ADR-0001). The backend never talks to Discord itself to verify roles.

We considered making the backend track its own admin list independently, matching the Captain treatment, but rejected it: it would be a second permission system running alongside Discord's own roles with no clear benefit, since admin-gated actions (creating a new Team/Player) are rare, low-frequency operations rather than the routine per-roster-change path Captain verification protects.

**Consequences:** `POST /teams` and `POST /players` require no caller-identity parameter at all — they trust that the score bot only exposes those commands to admins. `POST /teams/{id}/roster` requires a `requesting_discord_id` field the backend checks against `captain_discord_id`, and rejects the request if they don't match. One captain per team (not co-captains) — simplest fit for a single squadron lead, reversible later via a join table if that ever changes.
