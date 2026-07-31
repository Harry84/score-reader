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


async def attach_player_to_roster(client, team_id, requesting_discord_id, ref_player_id):
    return await client.post(
        f"/teams/{team_id}/roster",
        json={"requesting_discord_id": requesting_discord_id, "ref_player_id": ref_player_id},
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
