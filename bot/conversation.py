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


def render_error_detail(detail):
    """Formats a backend error response's `detail` for display - either a
    plain string (most errors) or the structured duplicate-match shape
    {"message": ..., "existing_match": ...} that POST /matches returns on a
    409 (ingestion.workflow.DuplicateMatchError)."""
    if isinstance(detail, dict) and "existing_match" in detail:
        return f"{detail['message']}:\n{render_match_summary(detail['existing_match'])}"
    return str(detail)


# Reaction the bot pre-adds to a screenshot, for an admin to click to trigger
# ingestion - see is_admin_reactor. INGESTED_EMOJI goes on the same message
# once the resulting match actually persists (ADR-0001). PROCESSING_EMOJI is
# added the instant an admin's trigger is accepted and removed once
# ingestion finishes (success, a follow-up question, or an error) - since
# extraction/persist takes a couple of seconds, this tells the admin their
# reaction was seen rather than leaving them wondering if it registered.
INGEST_TRIGGER_EMOJI = "\U0001F4E5"  # inbox tray emoji
INGESTED_EMOJI = "✅"  # white check mark emoji
PROCESSING_EMOJI = "⏳"  # hourglass (not done) emoji
CANCELLED_EMOJI = "❌"  # cross mark emoji


def is_admin_reactor(role_names, admin_role_name):
    """role_names: a Discord member's role names (any iterable of str) - the
    member reacting to a screenshot (main.py: on_raw_reaction_add) or the
    author of an admin-only command (main.py: _is_admin)."""
    return admin_role_name in role_names


def render_admin_required(admin_role_name):
    return f"Only a Discord user with the '{admin_role_name}' role can do that."


def render_screenshot_received():
    return (
        f"{INGEST_TRIGGER_EMOJI} Screenshot received - an admin can react with "
        f"{INGEST_TRIGGER_EMOJI} above to process this match."
    )


def render_question(question):
    text = _render_question_body(question)
    if not is_dead_end(question):
        text += "\n(Or reply `cancel` to abandon this screenshot.)"
    return text


def _render_question_body(question):
    qtype = question["type"]
    if qtype == "player_match":
        lines = [f"Couldn't match player '{question['player_name']}'. Did you mean:"]
        lines += [f"  {i}\\. {c['name']}" for i, c in enumerate(question["candidates"], start=1)]
        if not question["candidates"]:
            lines.append("(no close matches - ask an admin to add this player, then re-post the screenshot)")
        else:
            lines.append("  0\\. None of the above - it's a genuinely new player")
            lines.append("Reply with the number.")
        return "\n".join(lines)

    if qtype == "team_assignment":
        lines = [f"Which team is the {question['faction']} faction?"]
        lines += [f"  {i}\\. {c['name']}" for i, c in enumerate(question["candidates"], start=1)]
        if not question["candidates"]:
            lines.append("(no candidate teams found - ask an admin to resolve this manually)")
        else:
            lines.append("  0\\. None of the above - ask an admin to resolve this manually")
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


def render_cancelled():
    return f"{CANCELLED_EMOJI} Cancelled - this screenshot was not entered. Re-post it to try again."


def render_rejection(question):
    """Message shown after the user replies '0' to a player_match/
    team_assignment question - explicitly rejecting every fuzzy-matched
    candidate rather than picking a wrong one because it merely looked close."""
    if question["type"] == "player_match":
        return (
            f"OK - treating '{question['player_name']}' as a genuinely new player. "
            "Ask an admin to add them, then re-post the screenshot."
        )
    if question["type"] == "team_assignment":
        return f"OK - ask an admin to resolve the {question['faction']} team assignment manually."
    raise ValueError(f"Don't know how to render a rejection for a '{question['type']}' question.")


def is_dead_end(question):
    """True if this question has no candidate to reply with (e.g. an
    unrecognized player name with no fuzzy matches). Those are informational
    only - the fix happens out-of-band (admin adds the missing data, then
    the screenshot gets re-posted as a new match), not via a reply here.
    """
    return question["type"] in ("player_match", "team_assignment") and not question["candidates"]


def _parse_index(text, count):
    """Parses a reply to a candidate-numbered question: 1..count picks a
    candidate (returned as a 0-based index), 0 means "none of the above"
    (returned as None). Only reachable when count >= 1 - is_dead_end() keeps
    a zero-candidate question from ever being registered as answerable.
    """
    if not text.isdigit():
        raise ValueError(f"Reply with a number between 0 and {count}.")
    index = int(text)
    if not (0 <= index <= count):
        raise ValueError(f"Reply with a number between 0 and {count}.")
    return None if index == 0 else index - 1


def parse_answer(question, text):
    """Turn a plain-text reply into the answer payload submit_answer() expects.

    Returns None if the reply explicitly rejects every candidate ('0') - the
    caller should treat that as a dead end (render_rejection) rather than
    calling submit_answer. Raises ValueError with a user-facing message on
    unparseable input.
    """
    qtype = question["type"]
    text = text.strip()

    if qtype == "player_match":
        candidates = question["candidates"]
        index = _parse_index(text, len(candidates))
        return None if index is None else {"ref_player_id": candidates[index]["id"]}

    if qtype == "team_assignment":
        candidates = question["candidates"]
        index = _parse_index(text, len(candidates))
        return None if index is None else {"ref_team_id": candidates[index]["id"]}

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
        "`!create-team <name>` - create or find a team by name (Bot Admin only)",
        "`!set-captain <team_id> @discord_user` - assign a team's captain (Bot Admin only)",
        "`!add-roster <team_id> <player name>` - attach an existing player to a team's roster (that team's captain only)",
        "`!edit <match_id> <player name> <field>=<value> [...]` - correct a persisted match's stats",
        "`!edit-winner <match_id> <IMPERIAL|REBEL>` - correct a persisted match's winner",
        "",
        "**Editable fields for !edit** (combine several in one command):",
    ]
    lines += [
        f"  `{field}={example}`" for field, example in sorted(FIELD_EXAMPLES.items())
    ]
    return "\n".join(lines)
