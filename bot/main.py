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


async def _get_live_battle_context():
    """Ask the campaign project's read-only pending_battles endpoint which
    real campaign/turn/system a report should be tagged with, instead of
    config.DEFAULT_*. Returns (campaign_id, turn_id, system_id, note) --
    note is a short string worth telling the reporter (which system it
    picked, or why it fell back), or None if nothing's worth mentioning.
    Falls back to config.DEFAULT_* -- and says so -- whenever the campaign
    server is unreachable, nothing is currently pending, or
    config.BOT_USE_TEST_CAMPAIGN forces it. Never raises: an unreachable
    campaign server degrades to the old hardcoded behavior rather than
    blocking screenshot reporting entirely."""
    if config.BOT_USE_TEST_CAMPAIGN:
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID,
                config.DEFAULT_SYSTEM_ID, None)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{config.CAMPAIGN_API_URL}/api/pending_battles.json")
        resp.raise_for_status()
        pending = resp.json().get("pending_battles", [])
    except (httpx.HTTPError, ValueError):
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID, config.DEFAULT_SYSTEM_ID,
                "couldn't reach the live campaign -- tagged as the test-campaign default instead.")
    if not pending:
        return (config.DEFAULT_CAMPAIGN_ID, config.DEFAULT_TURN_ID, config.DEFAULT_SYSTEM_ID,
                "nothing's currently pending in the live campaign -- tagged as the test-campaign default instead.")
    # MVP: several systems can be contested in the same window at once
    # (see SQUADRONS-CAMPAIGN-DESIGN.md). Picking the lowest system_id
    # deterministically rather than asking which one is a real
    # simplification -- fine while a window is rarely more than one or two
    # contests deep, worth revisiting (a disambiguation question, same
    # shape as the existing pending-question flow) if that stops being true.
    chosen = min(pending, key=lambda p: p["system_id"])
    note = None
    if len(pending) > 1:
        others = ", ".join(p["system"] for p in pending if p is not chosen)
        note = f"multiple systems pending ({chosen['system']}, {others}) -- tagged to {chosen['system']}, first by id."
    return (chosen["campaign_id"], chosen["turn_id"], chosen["system_id"], note)


async def _handle_screenshot(message):
    attachment = message.attachments[0]
    image_bytes = await attachment.read()
    campaign_id, turn_id, system_id, note = await _get_live_battle_context()
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
        await message.reply("Usage: `!create-team <name>`")
        return
    response = await backend_client.create_team(http_client, name)
    if response.status_code != 200:
        await _reply_error(message, response)
        return
    team = response.json()
    await message.reply(f"Team '{team['name']}' ready (id `{team['id']}`).")


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
    if message.author == client.user or not _is_bot_channel(message):
        return

    pending = _pending_questions.get(message.channel.id)
    if pending is not None:
        await _handle_pending_answer(message, pending)
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
