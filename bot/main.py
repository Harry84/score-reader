"""Score bot (ROADMAP Phase 3, ADR-0001): minimal Discord bot proving the
screenshot -> persisted Match loop, plus the three team-onboarding commands
needed to set up rosters first. Only reacts in config.BOT_CHANNEL_NAME.

No slash commands, no reactions/buttons - plain text in, plain text out.
That polish is Phase 4.
"""

import discord
import httpx

from bot import backend_client, config
from bot.conversation import (
    CANCELLED_EMOJI,
    INGEST_TRIGGER_EMOJI,
    INGESTED_EMOJI,
    PROCESSING_EMOJI,
    is_admin_reactor,
    is_dead_end,
    parse_answer,
    parse_edit_command,
    parse_edit_updates,
    render_admin_required,
    render_cancelled,
    render_error_detail,
    render_help,
    render_match_summary,
    render_question,
    render_rejection,
    render_screenshot_received,
)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
http_client = None

# channel_id -> {"pending_match_id": int, "question": dict, "screenshot_message":
# discord.Message}. MVP: one in-flight question per channel, matching the
# roadmap's "next message's content back as the answer" flow - no multi-user
# concurrency handling.
_pending_questions = {}

# message_id -> discord.Message, for screenshots posted but not yet approved by
# an admin's INGEST_TRIGGER_EMOJI reaction. In-memory only, like
# _pending_questions - lost on restart, same accepted MVP limitation.
_pending_screenshots = {}

# channel_id -> {"match_id", "queue": [{"player", "role"}, ...],
# "screenshot_message"}. One player prompted at a time -- same "next
# message is the answer" shape as _pending_questions, kept separate since
# it starts only once a match has already reached "persisted" (the two
# never overlap for a given channel). In-memory only, lost on restart,
# same as the dicts above -- an interrupted review just leaves whatever
# roles were already confirmed; !edit still works standalone for the rest.
_role_review = {}

# channel_id -> {"campaign_id", "turn_id", "system_id", "system"}. Set by
# !report <system>, consumed (and cleared) by the next screenshot approved
# in that channel -- "ask what's pending, then say which one you're posting"
# instead of the bot guessing after the fact. In-memory only, lost on
# restart, same as the two dicts above.
_selected_battle = {}


def _is_bot_channel(message):
    return getattr(message.channel, "name", None) == config.BOT_CHANNEL_NAME


def _is_admin(message):
    role_names = (role.name for role in getattr(message.author, "roles", []))
    return is_admin_reactor(role_names, config.BOT_ADMIN_ROLE_NAME)


async def _reply_error(message, response):
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    await message.reply(f"Error ({response.status_code}): {render_error_detail(detail)}")


async def _handle_result(message, result, screenshot_message):
    status = result.get("status")
    if status == "persisted":
        await screenshot_message.add_reaction(INGESTED_EMOJI)
        await message.reply(render_match_summary(result))
        await _start_role_review(message, result)
        return
    if status and status.startswith("awaiting_"):
        question = result["question"]
        if not is_dead_end(question):
            _pending_questions[message.channel.id] = {
                "pending_match_id": result["pending_match_id"],
                "question": question,
                "screenshot_message": screenshot_message,
            }
        await message.reply(render_question(question))
        return
    await message.reply(f"Unexpected response: {result}")


ROLE_REVIEW_OPTIONS = ("Farmer", "Flex", "Support")


async def _start_role_review(message, result):
    """Right after a match persists: walk every player one at a time,
    offering to set THIS match's role, same shape as the old stats_reader
    CLI's "Enter new role for this match ... or press Enter to keep
    primary role" prompt -- brought into Discord since that per-match
    override step never survived the move off the old CLI. Never infers
    anything itself: shows exactly what's already on record (the player's
    primary_role, verbatim -- 'not set' if it's null) and only changes
    anything if a human actually types a role."""
    all_players = result["players"].get("rebel", []) + result["players"].get("imperial", [])
    if not all_players:
        return
    _role_review[message.channel.id] = {
        "match_id": result["match_id"],
        "queue": list(all_players),
    }
    await _prompt_next_role_review(message.channel)


async def _prompt_next_role_review(channel):
    review = _role_review.get(channel.id)
    if review is None:
        return
    if not review["queue"]:
        del _role_review[channel.id]
        await channel.send("Role review complete.")
        return
    player = review["queue"][0]
    current = player.get("role") or "not set"
    await channel.send(
        f"Role for **{player['player']}** this match -- currently *{current}*. "
        f"Type `{'`/`'.join(ROLE_REVIEW_OPTIONS)}` to set it, `keep` to leave it, "
        f"or `done` to stop reviewing."
    )


async def _handle_role_review_answer(message, review):
    text = message.content.strip()
    lowered = text.lower()
    if lowered == "done":
        del _role_review[message.channel.id]
        await message.reply("Role review stopped -- anything not yet reviewed keeps its current role.")
        return
    if lowered == "keep":
        review["queue"].pop(0)
        await _prompt_next_role_review(message.channel)
        return

    matched = next((r for r in ROLE_REVIEW_OPTIONS if r.lower() == lowered), None)
    if matched is None:
        await message.reply(f"'{text}' isn't `{'`/`'.join(ROLE_REVIEW_OPTIONS)}`, `keep`, or `done`. Try again.")
        return

    player = review["queue"][0]
    response = await backend_client.edit_match_player(
        http_client, review["match_id"], player["player"], {"role": matched})
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    review["queue"].pop(0)
    await message.reply(f"{player['player']} set to {matched} for this match.")
    await _prompt_next_role_review(message.channel)


async def _handle_pending_answer(message, pending):
    if message.content.strip().lower() == "cancel":
        response = await backend_client.cancel_match(http_client, pending["pending_match_id"])
        if response.status_code != 200:
            await _reply_error(message, response)
            return
        del _pending_questions[message.channel.id]
        await pending["screenshot_message"].add_reaction(CANCELLED_EMOJI)
        await message.reply(render_cancelled())
        return

    try:
        answer = parse_answer(pending["question"], message.content)
    except ValueError as e:
        await message.reply(str(e))
        return

    if answer is None:
        del _pending_questions[message.channel.id]
        await message.reply(render_rejection(pending["question"]))
        return

    response = await backend_client.submit_answer(
        http_client, pending["pending_match_id"], answer
    )
    if response.status_code != 200:
        await _reply_error(message, response)
        return

    del _pending_questions[message.channel.id]
    await _handle_result(message, response.json(), pending["screenshot_message"])


async def _fetch_pending_battles():
    """Raw GET against the campaign project's read-only pending_battles
    endpoint. Raises httpx.HTTPError/ValueError on any failure -- callers
    decide how to degrade, since !pending (report the failure) and
    _get_live_battle_context() (silently fall back) want different things
    from the same failure."""
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"{config.CAMPAIGN_API_URL}/api/pending_battles.json")
    resp.raise_for_status()
    return resp.json().get("pending_battles", [])


async def _handle_pending(message, rest):
    """!pending -- list what the live campaign is actually waiting on right
    now, so a reporter can !report a specific one before posting their
    screenshot instead of the bot guessing after the fact."""
    if config.BOT_USE_TEST_CAMPAIGN:
        await message.reply("Bot is in --test-campaign mode -- every report tags to the "
                            f"test-campaign default (system_id={config.DEFAULT_SYSTEM_ID}), "
                            "live campaign pending state isn't consulted.")
        return
    try:
        pending = await _fetch_pending_battles()
    except (httpx.HTTPError, ValueError):
        await message.reply(f"Couldn't reach the live campaign at {config.CAMPAIGN_API_URL}.")
        return
    if not pending:
        await message.reply("Nothing's currently pending in the live campaign.")
        return
    lines = [f"- **{p['system']}** (`{p['turn_id']}`)" for p in pending]
    await message.reply("Pending real match reports:\n" + "\n".join(lines)
                        + "\n\nUse `!report <system name>` to choose one before posting your screenshot.")


async def _handle_report(message, rest):
    """!report <system name> -- selects which pending battle the *next*
    screenshot approved in this channel should be tagged to (consumed and
    cleared the moment that screenshot is processed -- see
    _get_live_battle_context()). Matched case-insensitively, substring OK
    ('yavin' matches 'Yavin Prime') since these are always short, distinct
    system names."""
    name = rest.strip()
    if not name:
        await message.reply("Usage: `!report <system name>` -- see `!pending` for what's waiting.")
        return
    try:
        pending = await _fetch_pending_battles()
    except (httpx.HTTPError, ValueError):
        await message.reply(f"Couldn't reach the live campaign at {config.CAMPAIGN_API_URL}.")
        return
    matches = [p for p in pending if name.lower() in p["system"].lower()]
    if not matches:
        systems = ", ".join(p["system"] for p in pending) or "(nothing pending)"
        await message.reply(f"No pending battle matches '{name}'. Pending: {systems}")
        return
    if len(matches) > 1:
        names = ", ".join(p["system"] for p in matches)
        await message.reply(f"'{name}' matches more than one: {names}. Be more specific.")
        return
    chosen = matches[0]
    _selected_battle[message.channel.id] = chosen
    await message.reply(f"Locked in -- your next screenshot in this channel reports "
                        f"**{chosen['system']}** (`{chosen['turn_id']}`).")


class AmbiguousBattleError(Exception):
    """Several systems are pending and no !report selection was made --
    _handle_screenshot() must NOT guess (silently mistagging a real report
    as the test-campaign default is worse than just asking first), so this
    aborts ingestion entirely rather than falling back like every other
    degraded case below."""
    def __init__(self, systems):
        self.systems = systems


class AlreadyReportedError(Exception):
    """A real match already exists for this exact (campaign_id, turn_id,
    system_id) -- one match per system per turn, full stop, no do-overs by
    re-uploading a better screenshot. _handle_screenshot() must abort
    ingestion entirely, same discipline as AmbiguousBattleError above.
    Found live 2026-08-09: a since-fixed campaign_api_server.py bug (its
    WindowEngine had no campaign_client) let Yavin Prime keep showing as
    pending after a real match already existed for it, so a second
    screenshot silently persisted a second match for the same battle. That
    root cause is fixed, but this is the direct, explicit guarantee rather
    than relying on pending_battles happening to already exclude it."""
    def __init__(self, existing_match):
        self.existing_match = existing_match


async def _already_reported(campaign_id, turn_id, system_id):
    """True if a real match already exists for this exact scoping.
    Degrades to False (i.e. doesn't block) on any lookup failure -- an
    unreachable backend shouldn't itself be why a legitimate report gets
    rejected; create_match() will surface its own error if something's
    genuinely wrong."""
    try:
        resp = await backend_client.get_latest_match(
            http_client, config.CAMPAIGN_API_KEY, campaign_id, turn_id, system_id)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


async def _get_live_battle_context(channel_id):
    """Which real campaign/turn/system a report should be tagged with,
    instead of config.DEFAULT_*. Returns (campaign_id, turn_id, system_id,
    note) -- note is a short string worth telling the reporter, or None if
    nothing's worth mentioning. Raises AmbiguousBattleError (see above) if
    several battles are pending with no selection made, or
    AlreadyReportedError if a real match already exists for the chosen
    scoping -- the two cases this deliberately does NOT degrade to
    config.DEFAULT_* for.

    Priority: an explicit !report selection for this channel (consumed --
    cleared the moment it's used, so it only ever applies to the one
    screenshot it was made for) beats everything else. Absent one: exactly
    one pending battle is used automatically (nothing to actually choose);
    zero pending battles fall back to config.DEFAULT_* and say why. Same
    fallback whenever config.BOT_USE_TEST_CAMPAIGN forces it or the
    campaign server's unreachable."""
    if config.BOT_USE_TEST_CAMPAIGN:
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID,
                config.DEFAULT_SYSTEM_ID, None)

    selected = _selected_battle.pop(channel_id, None)
    if selected is not None:
        campaign_id, turn_id, system_id = selected["campaign_id"], selected["turn_id"], selected["system_id"]
        if await _already_reported(campaign_id, turn_id, system_id):
            raise AlreadyReportedError(selected)
        return (campaign_id, turn_id, system_id,
                f"reporting for your !report selection: {selected['system']}.")

    try:
        pending = await _fetch_pending_battles()
    except (httpx.HTTPError, ValueError):
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID, config.DEFAULT_SYSTEM_ID,
                "couldn't reach the live campaign -- tagged as the test-campaign default instead.")
    if not pending:
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID, config.DEFAULT_SYSTEM_ID,
                "nothing's currently pending in the live campaign -- tagged as the test-campaign default instead.")
    if len(pending) > 1:
        raise AmbiguousBattleError([p["system"] for p in pending])
    chosen = pending[0]
    if await _already_reported(chosen["campaign_id"], chosen["turn_id"], chosen["system_id"]):
        raise AlreadyReportedError(chosen)
    return (chosen["campaign_id"], chosen["turn_id"], chosen["system_id"], None)


async def _handle_screenshot(message):
    attachment = message.attachments[0]
    image_bytes = await attachment.read()
    try:
        campaign_id, turn_id, system_id, note = await _get_live_battle_context(message.channel.id)
    except AmbiguousBattleError as e:
        await message.reply(
            f"Multiple systems are pending ({', '.join(e.systems)}) and you haven't `!report`ed "
            "which one this is -- not tagging a guess. Run `!report <system name>`, then post the "
            "screenshot again.")
        return
    except AlreadyReportedError as e:
        await message.reply(
            f"**{e.existing_match['system']}** already has a match reported for this turn -- "
            "one match per system per turn. Not persisting a second one.")
        return
    if note:
        await message.reply(note)
    response = await backend_client.create_match(
        http_client,
        campaign_id=campaign_id,
        turn_id=turn_id,
        system_id=system_id,
        match_type=config.DEFAULT_MATCH_TYPE,
        screenshot_ref=f"discord://message/{message.id}",
        image_bytes=image_bytes,
        filename=attachment.filename,
    )
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    await _handle_result(message, response.json(), screenshot_message=message)


async def _handle_create_team(message, rest):
    if not _is_admin(message):
        await message.reply(render_admin_required(config.BOT_ADMIN_ROLE_NAME))
        return
    name = rest.strip()
    if not name:
        await message.reply("Usage: `!create-team <name> [faction]`")
        return
    # Optional trailing "rebel"/"imperial" token (IMPERIAL-MIRROR-BUILD-PLAN.md,
    # Dynamic Trust Alignment repo) -- not a separate arg slot, so a team name
    # that itself ends in one of those words can't be given a faction via this
    # command (create it unfactioned, then fix up faction directly if that
    # ever comes up).
    faction = None
    head, sep, tail = name.rpartition(" ")
    if sep and tail.lower() in ("rebel", "imperial") and head.strip():
        name, faction = head.strip(), tail.lower()
    response = await backend_client.create_team(http_client, name, faction=faction)
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    team = response.json()
    suffix = f" ({team['faction']})" if team.get("faction") else ""
    await message.reply(f"Team '{team['name']}'{suffix} ready (id `{team['id']}`).")


async def _handle_create_player(message, rest):
    if not _is_admin(message):
        await message.reply(render_admin_required(config.BOT_ADMIN_ROLE_NAME))
        return
    name = rest.strip()
    if not name:
        await message.reply("Usage: `!create-player <name>`")
        return
    response = await backend_client.create_player(http_client, name)
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    player = response.json()
    await message.reply(
        f"Player '{player['name']}' created (id `{player['id']}`). "
        "A captain can now `!add-roster` them to a team."
    )


async def _handle_set_captain(message, rest):
    if not _is_admin(message):
        await message.reply(render_admin_required(config.BOT_ADMIN_ROLE_NAME))
        return
    parts = rest.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit() or not message.mentions:
        await message.reply("Usage: `!set-captain <team_id> @discord_user`")
        return
    team_id = int(parts[0])
    captain = message.mentions[0]
    response = await backend_client.set_captain(http_client, team_id, str(captain.id))
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    await message.reply(f"{captain.mention} is now captain of team `{team_id}`.")


async def _handle_add_roster(message, rest):
    parts = rest.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.reply("Usage: `!add-roster <team_id> <player name>`")
        return
    team_id = int(parts[0])
    player_name = parts[1].strip()

    lookup = await backend_client.find_players(http_client, player_name)
    matches = lookup.json()
    if len(matches) != 1:
        if not matches:
            await message.reply(f"No player found matching '{player_name}'.")
        else:
            names = ", ".join(m["name"] for m in matches)
            await message.reply(f"Multiple players match '{player_name}': {names}. Be more specific.")
        return

    response = await backend_client.attach_player_to_roster(
        http_client, team_id, str(message.author.id), matches[0]["id"]
    )
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    await message.reply(f"Added '{matches[0]['name']}' to team `{team_id}`'s roster.")


async def _handle_edit_player(message, rest):
    try:
        match_id, player_name, edit_tokens = parse_edit_command(rest)
        updates = parse_edit_updates(edit_tokens)
    except ValueError as e:
        await message.reply(str(e))
        return

    response = await backend_client.edit_match_player(http_client, match_id, player_name, updates)
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    await message.reply(render_match_summary(response.json()))


async def _handle_edit_winner(message, rest):
    parts = rest.split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.reply("Usage: `!edit-winner <match_id> <IMPERIAL|REBEL>`")
        return
    match_id = int(parts[0])
    winner = parts[1]

    response = await backend_client.edit_match_winner(http_client, match_id, winner)
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    await message.reply(render_match_summary(response.json()))


async def _handle_help(message, rest):
    await message.reply(render_help())


COMMANDS = {
    "!create-team": _handle_create_team,
    "!create-player": _handle_create_player,
    "!set-captain": _handle_set_captain,
    "!add-roster": _handle_add_roster,
    "!edit": _handle_edit_player,
    "!edit-winner": _handle_edit_winner,
    "!pending": _handle_pending,
    "!report": _handle_report,
    "!help": _handle_help,
}


@client.event
async def on_ready():
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(base_url=config.BACKEND_URL, timeout=30)
    print(f"Logged in as {client.user} (channel: #{config.BOT_CHANNEL_NAME})")


@client.event
async def on_message(message):
    # message.author.bot (not just == client.user) -- another bot posting
    # into this same channel (e.g. the campaign Discord bot's battle
    # announcements) must never be picked up as an answer to a pending
    # question/role-review; found live when a battle-result line got
    # rejected as an invalid role-review answer instead of being ignored.
    if message.author.bot or not _is_bot_channel(message):
        return

    pending = _pending_questions.get(message.channel.id)
    if pending is not None:
        await _handle_pending_answer(message, pending)
        return

    review = _role_review.get(message.channel.id)
    if review is not None:
        await _handle_role_review_answer(message, review)
        return

    if message.attachments:
        _pending_screenshots[message.id] = message
        await message.reply(render_screenshot_received())
        await message.add_reaction(INGEST_TRIGGER_EMOJI)
        return

    command, _, rest = message.content.partition(" ")
    handler = COMMANDS.get(command)
    if handler is not None:
        await handler(message, rest)


@client.event
async def on_raw_reaction_add(payload):
    # payload.member is None for DM reactions, and is the bot itself right
    # after add_reaction() above adds INGEST_TRIGGER_EMOJI - both ignored.
    if payload.member is None or payload.member.bot:
        return
    if str(payload.emoji) != INGEST_TRIGGER_EMOJI:
        return
    message = _pending_screenshots.get(payload.message_id)
    if message is None:
        return
    role_names = (role.name for role in payload.member.roles)
    if not is_admin_reactor(role_names, config.BOT_ADMIN_ROLE_NAME):
        return

    # _pending_screenshots already stops the same message being processed
    # twice within one bot session (its entry is deleted below regardless of
    # whether _handle_screenshot succeeds or fails), but that dict is
    # in-memory only and lost on restart. Re-fetching the message and
    # checking for the bot's own INGESTED_EMOJI catches an already-ingested
    # screenshot even if that in-memory state is ever wrong - cheap next to
    # the alternative of silently re-hitting the paid Claude vision API.
    fresh_message = await message.channel.fetch_message(payload.message_id)
    already_ingested = any(
        str(reaction.emoji) == INGESTED_EMOJI and reaction.me
        for reaction in fresh_message.reactions
    )
    del _pending_screenshots[payload.message_id]
    if already_ingested:
        return

    await message.add_reaction(PROCESSING_EMOJI)
    try:
        await _handle_screenshot(message)
    finally:
        await message.remove_reaction(PROCESSING_EMOJI, client.user)


def main():
    client.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
