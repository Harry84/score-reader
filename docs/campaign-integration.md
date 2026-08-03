# Campaign project integration contract

What the score/stats backend (this repo) exposes to the campaign project
(NPC Commander), and the domain context needed to make sense of it. Written
for someone picking this up from the *other* project's side who has no
context on this repo. See `docs/adr/0001-discord-bot-split-and-push-notification.md`
for the architectural decision this contract implements, and `CONTEXT.md`
for the fuller vocabulary if a term below isn't enough.

## Ownership split (read this first)

Two separate Discord bots, split by write ownership, not by channel:

- **This project's "score bot"** is the *only* thing with write access to
  Team/Match data. It watches for screenshot uploads and team-admin
  commands, runs extraction, and persists Matches. Nothing in the campaign
  project ever writes here.
- **The campaign project's "narrative bot"** owns turn flow and
  trust/alignment-gated dialogue, and only ever *reads* Match/Team/stats
  data from this project - via the endpoints below, or the webhook this
  project pushes.

If the narrative flow needs something written here (a new Team, a new
canonical Player, a roster change), that's out of scope for this contract -
it goes through the score bot's Discord commands (`!create-team`,
`!create-player`, `!set-captain`, `!add-roster`), run by a human with the
right Discord role/captaincy, not through this API.

## Auth

Every endpoint below requires an `X-API-Key` header matching this backend's
`CAMPAIGN_API_KEY` (a static shared secret, config'd in this repo's `.env` -
ask for the current value out of band, it's not committed to either repo).
Missing or wrong key → `401 {"detail": "Invalid or missing API key"}`.

This is one-directional: it's the key *you* present to *us*. The outbound
webhook (below) carries a *different* key - the one *we* present to *you* -
so don't reuse one for the other.

## Domain concepts

- **Match** — one completed game, extracted from one screenshot: a winner,
  faction rosters, per-player stats. Always belongs to exactly one
  `(campaign_id, turn_id, system_id)`.
- **campaign_id** — an opaque string *you* own and generate. This project
  never interprets it, just stores it and scopes ELO by it. Pass the same
  value consistently for one time-boxed run of the whole war; a new
  campaign gets a fresh ELO ladder from scratch (ratings don't carry over).
- **turn_id** — an opaque string *you* own, identifying the gated
  leadup-to-a-game period a Match belongs to. **Not globally unique** -
  the same `turn_id` value can and does repeat across different
  `campaign_id`s, so always key lookups by `(campaign_id, turn_id, ...)`
  together, never `turn_id` alone.
- **system_id** — an integer FK into this project's small hand-seeded
  `systems` table (below). One of the 8 contested systems in the campaign's
  fixed map; a Match happens in exactly one system within one turn.
- **match_type** — `"team"` (scheduled squadron-vs-squadron, has real
  Team rosters on both sides), `"pickup"`, or `"ranked"` (ad-hoc rosters,
  no Team association - `player_stats.team_id`/roster concept doesn't
  apply). ELO is scored on separate, independent ladders per `match_type` -
  a player's pickup rating and ranked rating never mix.
- **Team** — a persistent named squadron (`!create-team` in Discord). A
  faction can have more than one standing Team. Only relevant for
  `match_type = "team"` matches.
- **Player** — canonical identity (`ref_players`), created via
  `!create-player`. A Player's `primary_team_id` is their *current* team
  assignment, independent of any specific Match's roster.
- **ELO** — computed synchronously after every Match persists, replaying
  the *entire* match history for that `(campaign_id[, match_type[, role]])`
  from scratch (not incremental) - so ratings are always internally
  consistent, never dependent on recompute order. Team ELO only exists for
  `match_type="team"`. Player ELO has a `"general"` base ladder plus three
  role sub-ladders (`"Flex"`, `"Support"`, `"Farmer"`) for `pickup`/`ranked`
  matches - a player who never plays a tracked role just never appears on
  that role's ladder (no entry, not a zero/default rating).

### Systems lookup (static, id → name)

| id | name |
|----|------|
| 1 | Nadiri Dockyards |
| 2 | Esseles |
| 3 | Zavian Abyss |
| 4 | Galitan |
| 5 | Sissubo |
| 6 | Yavin Prime |
| 7 | Fostar Haven |
| 8 | The Maw |

(id 7 - "Fostar Haven" - is still an open question upstream per the
campaign design; if it changes, this project's seed data changes, not this
contract's shape.)

## Endpoints

Base URL: wherever this backend is deployed (dev: `http://localhost:8001`).
All are `GET`, all require the `X-API-Key` header above.

---

### `GET /teams`

List every Team. No parameters.

```json
[
  {"id": 6, "name": "Test Squadron", "captain_discord_id": "408012460591808518"},
  {"id": 1, "name": "NWS", "captain_discord_id": null}
]
```

`captain_discord_id` is a raw Discord snowflake string, or `null` if no
captain's been assigned yet via `!set-captain`. Not useful to the campaign
project directly (it's a *Discord* identity, not something in your domain) -
included for completeness, not because you need to act on it.

---

### `GET /teams/{team_id}`

A single Team. `404 {"detail": "No team with id {id}"}` if it doesn't exist.

```json
{"id": 6, "name": "Test Squadron", "captain_discord_id": "408012460591808518"}
```

---

### `GET /teams/{team_id}/roster`

The Team's current players (by `ref_players.primary_team_id`, i.e. *right
now*, not "who played in some specific past Match" - see `players` in a
Match summary below for that). 404 with the same shape as above if the
team doesn't exist.

```json
[
  {"id": 12, "name": "Luke"},
  {"id": 85, "name": "Test McTestface"}
]
```

Empty list (not 404) if the team exists but has no players attached yet.

---

### `GET /matches/latest?campaign_id=&turn_id=&system_id=`

All three query params required. Returns the most recent (by internal
`match_date`) persisted Match for that exact `(campaign_id, turn_id,
system_id)` triple - "what happened in this system, this turn." `404` if
none exists yet (not an error condition worth alarming on - it just means
no Match has been reported for that combination yet).

```json
{
  "status": "persisted",
  "match_id": 28,
  "winner": "IMPERIAL",
  "turn_id": "webhook-verify",
  "system_id": 1,
  "campaign_id": "test-campaign",
  "match_type": "pickup",
  "players": {
    "imperial": [
      {
        "player": "NiWi-Side_Stack",
        "role": "Farmer",
        "score": 1501,
        "kills": 3,
        "deaths": 1,
        "assists": 0,
        "ai_kills": 10,
        "cap_ship_damage": 5000
      }
    ],
    "rebel": [
      {
        "player": "Hod",
        "role": "Flex",
        "score": 1200,
        "kills": 1,
        "deaths": 3,
        "assists": 0,
        "ai_kills": 5,
        "cap_ship_damage": 1000
      }
    ]
  }
}
```

`winner` is one of `"IMPERIAL"`, `"REBEL"`, or (rare, an ambiguous/unparseable
screenshot) `"UNKNOWN"`. `players.<faction>[].role` can be `null` - a
player's role is optional and not every match records one; treat `null` as
"no data," not an error. `match_id` is this project's internal integer PK -
stable, safe to store if you want to reference a specific Match later, but
not something you generate or predict.

This is the **exact same shape** the match-persisted webhook (below) sends
- if you ever miss a webhook delivery, polling this endpoint for the same
`(campaign_id, turn_id, system_id)` gets you the identical payload.

---

### `GET /elo/teams?campaign_id=`

Team ELO ladder for that campaign, ranked. Only ever has entries for
`match_type="team"` matches. Empty list if nothing's been played yet under
that `campaign_id` - not an error.

```json
[
  {
    "team_id": 3,
    "name": "181st",
    "rating": 1016.0,
    "matches_played": 1,
    "matches_won": 1,
    "matches_lost": 0,
    "rank": 1
  }
]
```

`rank` is 1-indexed, 1 = highest rating. `team_id` is this project's
internal PK (join target for `GET /teams/{id}` if you need the captain
etc. too - not returned inline here).

---

### `GET /elo/players?campaign_id=&match_type=&role=`

`campaign_id` and `match_type` (`"pickup"` or `"ranked"` - `"team"` player
ELO doesn't exist, only team ELO does) are required. `role` is optional,
**defaults to `"general"`** (the base ladder); pass `"Flex"`, `"Support"`,
or `"Farmer"` for a role-specific sub-ladder.

```json
[
  {
    "player_id": 20,
    "name": "Lions",
    "rating": 1065.907097378495,
    "matches_played": 7,
    "matches_won": 6,
    "matches_lost": 1,
    "rank": 1
  }
]
```

Same shape/semantics as the team ladder. A player who's never played that
`match_type` (or never played that specific role, for a role-scoped query)
simply won't appear - no zero-rating placeholder rows.

---

## Errors

Every non-2xx response is `{"detail": <string or object>}`, FastAPI's
default shape:

| Status | Meaning |
|---|---|
| 401 | Missing/wrong `X-API-Key` |
| 404 | The specific resource doesn't exist (bad team id, no roster, no match found) - not a fetch failure, just "nothing there yet" |
| 422 | A required query param was omitted or the wrong type (e.g. `system_id` not an integer) - FastAPI's standard validation shape, `{"detail": [{"loc": [...], "msg": ..., "type": ...}]}`, not the plain-string `detail` the other two use |

There's no 403/permission-tiering on any of these routes beyond the API
key - unlike the score bot's own write endpoints (captain/admin checks),
every read here is all-or-nothing once you're holding a valid key.

## The push side: match-persisted webhook

Independent of everything above - **you don't call anything to receive
this, we call you.** Once a Match is fully persisted (stats written, ELO
recomputed), this backend `POST`s the same JSON shape as
`GET /matches/latest` above to a URL you configure on our side
(`CAMPAIGN_WEBHOOK_URL` in this repo's `.env` - tell us the endpoint and
we'll set it, since **as of now it's unset and nothing is being sent yet**).

- Header: `X-API-Key: <CAMPAIGN_WEBHOOK_SECRET>` - a *different* key than
  the one you present to us for reads above. Verify it on your end if you
  want to confirm a request genuinely came from this backend.
- Retried up to 3 times (fixed 5s delay between attempts) on any transport
  error or non-2xx response from your endpoint. After that, we give up and
  log it - **there's no dead-letter queue or manual replay** on our side
  today. If you suspect a delivery was missed, `GET /matches/latest` for
  the `(campaign_id, turn_id, system_id)` you expect is the fallback -
  it'll return the identical payload once persisted, regardless of
  whether the webhook itself made it.
- Fires exactly once per Match, on its *first* persist only. If a Match is
  later corrected (`!edit`/`!edit-winner` in Discord - typo fixes, a
  misread stat), there's currently **no second "match updated" webhook** -
  the stored data changes, but you won't be re-notified. `GET /matches/latest`
  always reflects the current, possibly-corrected state if you poll it,
  but nothing pushes you the update.
- Respond `2xx` to any status code and body - we don't parse or care what
  you send back.

## What isn't covered here (known gaps, as of 2026-08-03)

- No webhook (or any push) for Match *edits* after initial persist - see
  above.
- No endpoint for a Team's `wins`/`losses` win-loss record directly (only
  ELO's `matches_played`/`matches_won`/`matches_lost`, which is the same
  underlying count but campaign-scoped rather than lifetime).
- No bulk/paginated variants of anything - `GET /teams` and the ELO ladder
  endpoints return everything in one response. Fine at current data
  volumes (single digits to low tens of teams/players); revisit if that
  changes.
- No rate limiting on any of these routes today - call responsibly, but
  there's no backend-enforced ceiling to worry about yet.
