import pytest

from bot.conversation import parse_answer, render_question


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


def test_parse_answer_rejects_non_numeric_for_player_match():
    question = {
        "type": "player_match",
        "player_name": "Wedg",
        "candidates": [{"id": 1, "name": "Wedge"}],
    }
    with pytest.raises(ValueError):
        parse_answer(question, "Wedge")
