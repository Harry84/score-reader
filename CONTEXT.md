# Squadrons Score Reader

Backend that extracts Star Wars Squadrons match data from screenshots, maintains canonical player/team identity, and computes stats and ELO ratings. Serving as the stats/state backend for a Discord-based game where an NPC Commander (a separate project) narrates turns based on match outcomes recorded here.

## Language

**Match**:
A single completed game, extracted from one screenshot, with a winner, faction rosters, and per-player stats. This is the existing canonical term in the schema (`matches` table) and stays canonical as the project becomes a Discord backend.
_Avoid_: Battle (this is what the Discord-facing game calls a Match from its point of view, but the codebase and internal docs use Match consistently — do not introduce Battle as a second term for the same thing).

**Turn**:
The gated leadup-to-a-game period, owned and tracked entirely by the NPC Commander project. This project does not model Turn's lifecycle or gating — it only persists the turn's external identifier as a reference on a Match, so multiple Matches can be grouped by the turn they belong to.

**Team**:
A persistent, named squadron — unchanged from the existing `ref_teams`/`teams` concept. Created via a Discord command backed by the reference database (not a new roster concept). A faction can have more than one standing Team; a Team's players are canonical `ref_players` records.

**Faction**:
One of the two overarching campaign sides (Imperial/Rebel), each with its own commander and Discord channel. Orthogonal to Team: a Match is one Team's roster (or players assigned for that side) playing under a Faction, in a specific System, within a Turn.

**System**:
One of the 8 contested star systems in the wider game's fixed cube-shaped map (7 named systems + The Maw) — becomes contested when both factions' capital ship slots are occupied there. A Match belongs to exactly one System within a Turn; the pair (turn_id, system_id) is what identifies which contested system a given Match's outcome applies to in the overall turn history. Unlike Turn, the set of Systems is small and essentially static, so this project keeps its own minimal hand-seeded lookup (id + name) for validation and human-readable reporting, rather than treating system_id as a fully opaque value or syncing it from the other project.
