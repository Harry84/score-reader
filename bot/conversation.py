"""Pure rendering/parsing for the score bot's plain-text ambiguity Q&A
(ROADMAP Phase 3). Decoupled from discord.py and the backend HTTP client so
it can be unit-tested against the same question shapes ingestion/workflow.py
produces, without a real Discord message or a running backend.
"""


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

    if qtype == "role":
        lines = [f"What role does '{question['player_name']}' play?"]
        lines += [f"  {i}. {c}" for i, c in enumerate(question["candidates"], start=1)]
        lines.append("Reply with the role name or its number.")
        return "\n".join(lines)

    if qtype == "team_assignment":
        lines = [f"Which team is the {question['faction']} faction?"]
        lines += [f"  {i}. {c['name']}" for i, c in enumerate(question["candidates"], start=1)]
        if not question["candidates"]:
            lines.append("(no candidate teams found - ask an admin to resolve this manually)")
        else:
            lines.append("Reply with the number.")
        return "\n".join(lines)

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
    candidates = question["candidates"]
    text = text.strip()

    if qtype == "player_match":
        return {"ref_player_id": candidates[_parse_index(text, len(candidates))]["id"]}

    if qtype == "team_assignment":
        return {"ref_team_id": candidates[_parse_index(text, len(candidates))]["id"]}

    if qtype == "role":
        if text.isdigit():
            return {"role": candidates[_parse_index(text, len(candidates))]}
        matched = next((c for c in candidates if c.lower() == text.lower()), None)
        if matched is None:
            raise ValueError(f"'{text}' isn't a valid role. Choose one of: {', '.join(candidates)}")
        return {"role": matched}

    raise ValueError(f"Don't know how to answer a '{qtype}' question yet.")
