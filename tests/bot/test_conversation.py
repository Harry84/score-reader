import pytest

from bot.conversation import (
    EDITABLE_PLAYER_FIELDS,
    parse_answer,
    parse_edit_command,
    parse_edit_updates,
    render_help,
    render_match_summary,
    render_question,
)


def test_render_player_match_question_lists_candidates():
    question = {
        "type": "player_match",
        "player_name": "Wedg",
        "candidates": [{"id": 1, "name": "Wedge"}, {"id": 2, "name": "Wedgy"}],
    }
    text = render_question(question)
    assert "Wedg" in text
    assert "1. Wedge" in text
    assert "2. Wedgy" in text


def test_render_player_match_question_with_no_candidates():
    question = {"type": "player_match", "player_name": "Nobody", "candidates": []}
    text = render_question(question)
    assert "no close matches" in text


def test_render_role_question_lists_candidates():
    question = {"type": "role", "player_name": "Wedge", "candidates": ["Farmer", "Flex", "Support"]}
    text = render_question(question)
    assert "1. Farmer" in text
    assert "2. Flex" in text
    assert "3. Support" in text


def test_render_team_assignment_question_lists_candidates():
    question = {
        "type": "team_assignment",
        "faction": "rebel",
        "candidates": [{"id": 5, "name": "Rogue Squadron"}],
    }
    text = render_question(question)
    assert "rebel" in text
    assert "1. Rogue Squadron" in text


def test_parse_answer_player_match_selects_candidate_by_number():
    question = {
        "type": "player_match",
        "player_name": "Wedg",
        "candidates": [{"id": 1, "name": "Wedge"}, {"id": 2, "name": "Wedgy"}],
    }
    assert parse_answer(question, "2") == {"ref_player_id": 2}


def test_parse_answer_team_assignment_selects_candidate_by_number():
    question = {
        "type": "team_assignment",
        "faction": "rebel",
        "candidates": [{"id": 5, "name": "Rogue Squadron"}],
    }
    assert parse_answer(question, "1") == {"ref_team_id": 5}


def test_parse_answer_role_accepts_name_case_insensitive():
    question = {"type": "role", "player_name": "Wedge", "candidates": ["Farmer", "Flex", "Support"]}
    assert parse_answer(question, "flex") == {"role": "Flex"}


def test_parse_answer_role_accepts_number():
    question = {"type": "role", "player_name": "Wedge", "candidates": ["Farmer", "Flex", "Support"]}
    assert parse_answer(question, "2") == {"role": "Flex"}


def test_parse_answer_role_rejects_unknown_role():
    question = {"type": "role", "player_name": "Wedge", "candidates": ["Farmer", "Flex", "Support"]}
    with pytest.raises(ValueError):
        parse_answer(question, "Pilot")


def test_parse_answer_rejects_out_of_range_number():
    question = {
        "type": "player_match",
        "player_name": "Wedg",
        "candidates": [{"id": 1, "name": "Wedge"}],
    }
    with pytest.raises(ValueError):
        parse_answer(question, "5")


def test_render_match_summary_includes_winner_and_both_factions():
    result = {
        "status": "persisted",
        "match_id": 42,
        "winner": "IMPERIAL",
        "players": {
            "imperial": [
                {
                    "player": "Vader",
                    "role": "Flex",
                    "score": 1675,
                    "kills": 4,
                    "deaths": 2,
                    "assists": 1,
                    "ai_kills": 18,
                    "cap_ship_damage": 30139,
                },
            ],
            "rebel": [
                {
                    "player": "Wedge",
                    "role": "Support",
                    "score": 1200,
                    "kills": 2,
                    "deaths": 4,
                    "assists": 0,
                    "ai_kills": 10,
                    "cap_ship_damage": 0,
                },
            ],
        },
    }
    text = render_match_summary(result)
    assert "42" in text
    assert "IMPERIAL" in text
    assert "Vader" in text
    assert "Wedge" in text
    assert "30139" in text


def test_render_match_summary_skips_empty_faction():
    result = {
        "status": "persisted",
        "match_id": 1,
        "winner": "REBEL",
        "players": {
            "imperial": [],
            "rebel": [
                {
                    "player": "Wedge",
                    "role": None,
                    "score": 0,
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "ai_kills": 0,
                    "cap_ship_damage": 0,
                }
            ],
        },
    }
    text = render_match_summary(result)
    assert "IMPERIAL" not in text
    assert "Wedge" in text


def test_parse_answer_rejects_non_numeric_for_player_match():
    question = {
        "type": "player_match",
        "player_name": "Wedg",
        "candidates": [{"id": 1, "name": "Wedge"}],
    }
    with pytest.raises(ValueError):
        parse_answer(question, "Wedge")


def test_parse_edit_command_splits_match_id_player_name_and_edits():
    match_id, player_name, edit_tokens = parse_edit_command("42 Vader score=1700 kills=5")
    assert match_id == 42
    assert player_name == "Vader"
    assert edit_tokens == ["score=1700", "kills=5"]


def test_parse_edit_command_handles_player_name_with_spaces():
    match_id, player_name, edit_tokens = parse_edit_command("42 Not Tom score=1700")
    assert match_id == 42
    assert player_name == "Not Tom"
    assert edit_tokens == ["score=1700"]


def test_parse_edit_command_rejects_missing_match_id():
    with pytest.raises(ValueError):
        parse_edit_command("Vader score=1700")


def test_parse_edit_command_rejects_missing_player_name():
    with pytest.raises(ValueError):
        parse_edit_command("42 score=1700")


def test_parse_edit_updates_coerces_numeric_fields():
    assert parse_edit_updates(["score=1700", "kills=5"]) == {"score": 1700, "kills": 5}


def test_parse_edit_updates_keeps_name_and_role_as_strings():
    assert parse_edit_updates(["name=Tarkin", "role=Support"]) == {
        "name": "Tarkin",
        "role": "Support",
    }


def test_parse_edit_updates_rejects_unknown_field():
    with pytest.raises(ValueError):
        parse_edit_updates(["favorite_color=red"])


def test_parse_edit_updates_rejects_non_numeric_value_for_numeric_field():
    with pytest.raises(ValueError):
        parse_edit_updates(["score=a-lot"])


def test_parse_edit_updates_rejects_malformed_token():
    with pytest.raises(ValueError):
        parse_edit_updates(["score"])


def test_parse_edit_updates_rejects_empty_tokens():
    with pytest.raises(ValueError):
        parse_edit_updates([])


def test_render_help_lists_all_commands_and_every_editable_field():
    text = render_help()
    for command in ("!create-team", "!set-captain", "!add-roster", "!edit", "!edit-winner"):
        assert command in text
    for field in EDITABLE_PLAYER_FIELDS:
        assert f"{field}=" in text
