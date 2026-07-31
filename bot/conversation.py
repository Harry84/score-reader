"""Pure rendering/parsing for the score bot's plain-text ambiguity Q&A
(ROADMAP Phase 3). Decoupled from discord.py and the backend HTTP client so
it can be unit-tested against the same question shapes ingestion/workflow.py
produces, without a real Discord message or a running backend.
"""


def render_match_summary(result):
    """Post-persist confirmation table, re-rendered after !edit too."""
    lines = [f"Match `{result['match_id']}` persisted - winner: {result['winner']}"]
    for faction in ("imperial", "rebel"):
        players = result["players"].get(faction, [])
        if not players:
            continue
        lines.append(f"\n**{faction.upper()}**")
        lines.append("```")
        lines.append(
            f"{'Player':<20}{'Role':<10}{'Score':>6}{'K':>4}{'D':>4}{'A':>4}{'AI':>5}{'CapDmg':>8}"
        )
        for p in players:
            role = p["role"] or "-"
            lines.append(
                f"{p['player']:<20}{role:<10}{p['score']:>6}{p['kills']:>4}{p['deaths']:>4}"
                f"{p['assists']:>4}{p['ai_kills']:>5}{p['cap_ship_damage']:>8}"
            )
        lines.append("```")
    return "\n".join(lines)


def render_question(question):
    qtype = question["type"]
    if qtype == "player_match":
        lines = [f"Couldn't match player '{question['player_name']}'. Did you mean:"]
        lines += [f"  {i}. {c['name']}" for i, c in enumerate(question["candidates"], start=1)]
        if not question["candidates"]:
            lines.append("(no close matches - ask an admin to add this player, then re-post the screenshot)")
        else:
            lines.append("Reply with the number.")
        return "\n".join(lines)

    if qtype == "team_assignment":
        lines = [f"Which team is the {question['faction']} faction?"]
        lines += [f"  {i}. {c['name']}" for i, c in enumerate(question["candidates"], start=1)]
        if not question["candidates"]:
            lines.append("(no candidate teams found - ask an admin to resolve this manually)")
        else:
            lines.append("Reply with the number.")
        return "\n".join(lines)

    if qtype == "roster_size":
        return (
            f"{question['faction'].capitalize()} team has {question['count']} players, "
            f"expected {question['expected']}. Reply `confirm` to proceed anyway."
        )

    if qtype == "missing_field":
        kind = "a number" if question["numeric"] else "a value"
        return f"'{question['player_name']}' is missing '{question['field']}'. Reply with {kind}."

    raise ValueError(f"Don't know how to render a '{qtype}' question yet.")


def _parse_index(text, count):
    if not text.isdigit():
        raise ValueError(f"Reply with a number between 1 and {count}.")
    index = int(text)
    if not (1 <= index <= count):
        raise ValueError(f"Reply with a number between 1 and {count}.")
    return index - 1


def parse_answer(question, text):
    """Turn a plain-text reply into the answer payload submit_answer() expects.

    Raises ValueError with a user-facing message on unparseable input.
    """
    qtype = question["type"]
    text = text.strip()

    if qtype == "player_match":
        candidates = question["candidates"]
        return {"ref_player_id": candidates[_parse_index(text, len(candidates))]["id"]}

    if qtype == "team_assignment":
        candidates = question["candidates"]
        return {"ref_team_id": candidates[_parse_index(text, len(candidates))]["id"]}

    if qtype == "roster_size":
        if text.lower() != "confirm":
            raise ValueError("Reply `confirm` to proceed with this roster size.")
        return {"confirm": True}

    if qtype == "missing_field":
        if question["numeric"]:
            if not text.lstrip("-").isdigit():
                raise ValueError(f"'{question['field']}' must be a number, got '{text}'.")
            return {"value": int(text)}
        return {"value": text}

    raise ValueError(f"Don't know how to answer a '{qtype}' question yet.")


# Mirrors ingestion.workflow.EDITABLE_PLAYER_FIELDS plus "name" (a reassignment,
# not a raw column write - see edit_match_player), matching the field set
# stats_reader/data_cleaner.py's old pre-DB CLI review step let you correct.
EDITABLE_PLAYER_FIELDS = {"name", "role", "score", "kills", "deaths", "assists", "ai_kills", "cap_ship_damage"}
NUMERIC_PLAYER_FIELDS = {"score", "kills", "deaths", "assists", "ai_kills", "cap_ship_damage"}

# role=none (or null/-) clears a match's role entirely, e.g. a genuine
# multi-role match that doesn't fit one bucket - "no role" is a legitimate
# persisted state (ingestion.workflow no longer pauses to force one), not
# an error.
NO_ROLE_SENTINELS = {"none", "null", "-"}

# One example value per editable field, used by render_help() - kept next to
# EDITABLE_PLAYER_FIELDS so a new field can't be added without also getting
# a help example.
FIELD_EXAMPLES = {
    "name": "Tarkin",
    "role": "Support (or 'none' to clear it)",
    "score": "1999",
    "kills": "5",
    "deaths": "2",
    "assists": "1",
    "ai_kills": "12",
    "cap_ship_damage": "15000",
}
assert set(FIELD_EXAMPLES) == EDITABLE_PLAYER_FIELDS


def parse_edit_command(rest):
    """Split '<match_id> <player name> field=value ...' into
    (match_id, player_name, edit_tokens). Player names may contain spaces;
    field=value tokens (which never do) mark where the name ends.
    """
    parts = rest.split()
    if not parts or not parts[0].isdigit():
        raise ValueError("Usage: `!edit <match_id> <player_name> <field>=<value> [...]`")
    match_id = int(parts[0])

    rest_parts = parts[1:]
    split_index = next((i for i, p in enumerate(rest_parts) if "=" in p), len(rest_parts))
    if split_index == 0:
        raise ValueError("Usage: `!edit <match_id> <player_name> <field>=<value> [...]`")

    player_name = " ".join(rest_parts[:split_index])
    edit_tokens = rest_parts[split_index:]
    return match_id, player_name, edit_tokens


def parse_edit_updates(tokens):
    """Turn ['score=1700', 'kills=5'] into {'score': 1700, 'kills': 5}."""
    if not tokens:
        raise ValueError("No field=value edits given.")

    updates = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"'{token}' isn't in field=value form.")
        field, _, value = token.partition("=")
        if field not in EDITABLE_PLAYER_FIELDS:
            raise ValueError(
                f"Can't edit '{field}'. Editable fields: {', '.join(sorted(EDITABLE_PLAYER_FIELDS))}"
            )
        if field == "role" and value.lower() in NO_ROLE_SENTINELS:
            value = None
        elif field in NUMERIC_PLAYER_FIELDS:
            if not value.lstrip("-").isdigit():
                raise ValueError(f"'{field}' must be a number, got '{value}'.")
            value = int(value)
        updates[field] = value
    return updates


def render_help():
    lines = [
        "**Commands**",
        "`!create-team <name>` - create or find a team by name",
        "`!set-captain <team_id> @discord_user` - assign a team's captain",
        "`!add-roster <team_id> <player name>` - attach an existing player to a team's roster",
        "`!edit <match_id> <player name> <field>=<value> [...]` - correct a persisted match's stats",
        "`!edit-winner <match_id> <IMPERIAL|REBEL>` - correct a persisted match's winner",
        "",
        "**Editable fields for !edit** (combine several in one command):",
    ]
    lines += [
        f"  `{field}={example}`" for field, example in sorted(FIELD_EXAMPLES.items())
    ]
    return "\n".join(lines)
