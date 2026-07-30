---
status: accepted
---

# Ambiguity resolution moves from terminal prompts to blocking Discord interaction

The existing pipeline (`stats_db_processor_direct.py` and friends) resolves every ambiguous case — unrecognized player name, match type, subbing status, role — by blocking on a terminal prompt to a human operator. That model has no equivalent once ingestion is triggered by a screenshot dropped in Discord; there's no terminal. We considered making the pipeline always guess automatically (highest-confidence fuzzy match, inferred match type) and queue anything uncertain for later admin review, but rejected it: getting player identity or match type wrong corrupts stats/ELO history, and this game's Discord-native audience expects a quick answer, not a stats correction days later.

Instead, when the score bot hits genuine ambiguity during ingestion, it asks in the originating Discord channel (buttons/reactions/a follow-up message) and blocks that Match's persistence until answered — moving the confirmation UI from terminal to Discord rather than removing it. Because team rosters are now established up front at team-creation time (players linked to canonical `ref_players`, scoped to a channel/faction), we expect this to fire far less often than the current CLI flow, not as often as one prompt per field.

**Consequences:** ingestion becomes asynchronous/stateful rather than a single request/response — a Match can sit in a "pending clarification" state waiting on a Discord reply. The score bot and the ingestion API need a shared way to represent "this Match is blocked on human input" and resume processing once it arrives.
