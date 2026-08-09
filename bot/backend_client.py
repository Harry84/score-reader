"""Thin async HTTP wrapper over the backend API (ROADMAP Phases 1-3).

Each function returns the raw httpx.Response - callers decide how to handle
non-200 status codes (e.g. relaying response.json()["detail"] to Discord),
matching how api/teams.py and api/main.py report errors.
"""


async def create_team(client, name):
    return await client.post("/teams", json={"name": name})


async def set_captain(client, team_id, captain_discord_id):
    return await client.post(
        f"/teams/{team_id}/captain", json={"captain_discord_id": captain_discord_id}
    )


async def find_players(client, name):
    return await client.get("/players", params={"name": name})


async def create_player(client, name):
    return await client.post("/players", json={"name": name})


async def attach_player_to_roster(client, team_id, requesting_discord_id, ref_player_id):
    return await client.post(
        f"/teams/{team_id}/roster",
        json={"requesting_discord_id": requesting_discord_id, "ref_player_id": ref_player_id},
    )


async def get_latest_match(client, campaign_api_key, campaign_id, turn_id, system_id):
    """GET /matches/latest -- the same campaign-project read route
    CampaignClient.get_latest_match() uses (api/reads.py), gated behind
    require_campaign_api_key unlike every other route here, so this is the
    one call on this client that needs an explicit X-API-Key header rather
    than the bot's own auth. Used to check "has this exact battle already
    been reported" before persisting a new one -- see main.py's
    AlreadyReportedError."""
    return await client.get(
        "/matches/latest",
        params={"campaign_id": campaign_id, "turn_id": turn_id, "system_id": system_id},
        headers={"X-API-Key": campaign_api_key},
    )


async def create_match(
    client, campaign_id, turn_id, system_id, match_type, screenshot_ref, image_bytes, filename
):
    return await client.post(
        "/matches",
        data={
            "campaign_id": campaign_id,
            "turn_id": turn_id,
            "system_id": str(system_id),
            "match_type": match_type,
            "screenshot_ref": screenshot_ref,
        },
        files={"image": (filename, image_bytes)},
    )


async def submit_answer(client, pending_match_id, answer):
    return await client.post(f"/matches/{pending_match_id}/answer", json={"answer": answer})


async def cancel_match(client, pending_match_id):
    return await client.post(f"/matches/{pending_match_id}/cancel")


async def edit_match_player(client, match_id, player_name, updates):
    return await client.patch(
        f"/matches/{match_id}/players/{player_name}", json={"updates": updates}
    )


async def edit_match_winner(client, match_id, winner):
    return await client.patch(f"/matches/{match_id}/winner", json={"winner": winner})
