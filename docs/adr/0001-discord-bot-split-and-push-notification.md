---
status: accepted
---

# Two Discord bots split by domain ownership, integrated by push notification

This project (score/stats backend) and the NPC Commander project each own a separate Discord bot, split by write ownership rather than by channel: this project's "score bot" is the only Discord surface with write access to Team/Match data — it watches the two faction channels for screenshot attachments and team-admin commands, runs extraction, persists the Match, and reacts on the source message to acknowledge ingestion. The NPC Commander project's "narrative bot" owns the trust/alignment-gated dialogue and turn flow, and only *reads* Match/stats data from this project — it never writes here. We considered a single bot spanning both domains, but that would mix score-parsing/team-admin logic with narrative/trust-gating logic in one process and force a synchronous call path into this project for every gated interaction.

When this backend finishes persisting a Match (score parsed, stats/ELO recalculated), it pushes a webhook/event to the NPC Commander project ("Match ready for turn X") rather than requiring that project to poll, since the narrative bot needs to react promptly to keep pace with the turn's gated flow.

**Consequences:** this project owns the config/credentials for calling the other project's webhook endpoint (the only place this project depends on the other project's runtime location). Reads flow the opposite direction, via this project's own read API, so the dependency is not circular. Both bots run in the same Discord server against the same two faction channels with disjoint command/event sets — care is needed so neither bot reacts to or handles messages owned by the other.
