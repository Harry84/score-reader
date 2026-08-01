import asyncio
import json

import httpx

from bot import backend_client


def _run(coro):
    return asyncio.run(coro)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://backend")


def test_create_team_posts_name():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1, "name": "Rogue Squadron"})

    async def run():
        async with _client(handler) as client:
            return await backend_client.create_team(client, "Rogue Squadron")

    response = _run(run())

    assert response.status_code == 200
    assert captured == {"method": "POST", "url": "/teams", "json": {"name": "Rogue Squadron"}}


def test_find_players_sends_name_query_param():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": 1, "name": "Wedge"}])

    async def run():
        async with _client(handler) as client:
            return await backend_client.find_players(client, "Wedge")

    response = _run(run())

    assert response.status_code == 200
    assert "name=Wedge" in captured["url"]
    assert response.json() == [{"id": 1, "name": "Wedge"}]


def test_attach_player_to_roster_posts_requesting_discord_id_and_player_id():
    captured = {}

    def handler(request):
        captured["url"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "attached"})

    async def run():
        async with _client(handler) as client:
            return await backend_client.attach_player_to_roster(client, 3, "discord-user-1", 7)

    response = _run(run())

    assert response.status_code == 200
    assert captured["url"] == "/teams/3/roster"
    assert captured["json"] == {"requesting_discord_id": "discord-user-1", "ref_player_id": 7}


def test_create_match_sends_multipart_form_and_image():
    captured = {}

    def handler(request):
        captured["url"] = request.url.path
        captured["content_type"] = request.headers["content-type"]
        return httpx.Response(200, json={"status": "persisted", "match_id": 42})

    async def run():
        async with _client(handler) as client:
            return await backend_client.create_match(
                client,
                campaign_id="campaign-1",
                turn_id="turn-1",
                system_id=1,
                match_type="pickup",
                screenshot_ref="discord://message/123",
                image_bytes=b"fake-bytes",
                filename="screenshot.png",
            )

    response = _run(run())

    assert response.status_code == 200
    assert captured["url"] == "/matches"
    assert captured["content_type"].startswith("multipart/form-data")
    assert response.json() == {"status": "persisted", "match_id": 42}


def test_submit_answer_wraps_answer_in_body():
    captured = {}

    def handler(request):
        captured["url"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "persisted", "match_id": 1})

    async def run():
        async with _client(handler) as client:
            return await backend_client.submit_answer(client, 9, {"ref_player_id": 2})

    response = _run(run())

    assert response.status_code == 200
    assert captured["url"] == "/matches/9/answer"
    assert captured["json"] == {"answer": {"ref_player_id": 2}}


def test_cancel_match_posts_to_cancel_endpoint():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = request.url.path
        return httpx.Response(200, json={"status": "cancelled", "pending_match_id": 9})

    async def run():
        async with _client(handler) as client:
            return await backend_client.cancel_match(client, 9)

    response = _run(run())

    assert response.status_code == 200
    assert captured == {"method": "POST", "url": "/matches/9/cancel"}


def test_edit_match_player_patches_updates_for_named_player():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "persisted", "match_id": 1})

    async def run():
        async with _client(handler) as client:
            return await backend_client.edit_match_player(client, 1, "Vader", {"score": 2000})

    response = _run(run())

    assert response.status_code == 200
    assert captured == {
        "method": "PATCH",
        "url": "/matches/1/players/Vader",
        "json": {"updates": {"score": 2000}},
    }


def test_edit_match_winner_patches_winner_field():
    captured = {}

    def handler(request):
        captured["url"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "persisted", "match_id": 1, "winner": "REBEL"})

    async def run():
        async with _client(handler) as client:
            return await backend_client.edit_match_winner(client, 1, "REBEL")

    response = _run(run())

    assert response.status_code == 200
    assert captured["url"] == "/matches/1/winner"
    assert captured["json"] == {"winner": "REBEL"}
