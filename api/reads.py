"""Campaign-project read routes (ROADMAP Phase 5, ADR-0001): the narrative
bot only ever reads Match/Team/stats data from this project, never writes -
all routes here are gated behind require_campaign_api_key.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_campaign_api_key
from api.dependencies import get_pg_conn
from ingestion.workflow import get_latest_match
from stats.history import get_match_detail, get_matchup, list_seasons
from stats.player_elo import GENERAL as PLAYER_ELO_GENERAL
from stats.player_elo import get_player_elo_ladder
from stats.player_history import get_player_career, get_player_elo_history, get_stat_leaders
from stats.team_elo import get_team_elo_ladder
from teams.onboarding import get_team_roster

router = APIRouter(dependencies=[Depends(require_campaign_api_key)])


@router.get("/teams/{team_id}/roster")
def get_team_roster_route(team_id: int, pg_conn=Depends(get_pg_conn)):
    try:
        return get_team_roster(pg_conn, team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/matches/latest")
def get_latest_match_route(
    campaign_id: str, turn_id: str, system_id: int, pg_conn=Depends(get_pg_conn)
):
    match = get_latest_match(pg_conn, campaign_id, turn_id, system_id)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"No match for campaign_id={campaign_id!r} turn_id={turn_id!r} system_id={system_id!r}",
        )
    return match


@router.get("/matches/{match_id}")
def get_match_detail_route(match_id: int, pg_conn=Depends(get_pg_conn)):
    match = get_match_detail(pg_conn, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"No match with id {match_id}")
    return match


@router.get("/seasons")
def list_seasons_route(pg_conn=Depends(get_pg_conn)):
    return list_seasons(pg_conn)


@router.get("/matchups")
def get_matchup_route(
    team_a: str,
    team_b: str,
    season_id: int | None = None,
    campaign_id: str | None = None,
    pg_conn=Depends(get_pg_conn),
):
    try:
        return get_matchup(pg_conn, team_a, team_b, season_id, campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/elo/teams")
def get_team_elo_ladder_route(campaign_id: str, pg_conn=Depends(get_pg_conn)):
    return get_team_elo_ladder(pg_conn, campaign_id)


@router.get("/elo/players")
def get_player_elo_ladder_route(
    campaign_id: str,
    match_type: str,
    role: str = PLAYER_ELO_GENERAL,
    pg_conn=Depends(get_pg_conn),
):
    return get_player_elo_ladder(pg_conn, campaign_id, match_type, role)


@router.get("/elo/players/history")
def get_player_elo_history_route(
    campaign_id: str,
    player: str,
    match_type: str,
    role: str = PLAYER_ELO_GENERAL,
    pg_conn=Depends(get_pg_conn),
):
    try:
        return get_player_elo_history(pg_conn, campaign_id, player, match_type, role)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/players/career")
def get_player_career_route(
    player: str,
    campaign_id: str | None = None,
    match_type: str | None = None,
    pg_conn=Depends(get_pg_conn),
):
    try:
        return get_player_career(pg_conn, player, campaign_id, match_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stats/leaders")
def get_stat_leaders_route(
    stat: str,
    per: str = "total",
    campaign_id: str | None = None,
    match_type: str | None = None,
    role: str | None = None,
    min_matches: int = 1,
    limit: int = 10,
    pg_conn=Depends(get_pg_conn),
):
    try:
        return get_stat_leaders(pg_conn, stat, per, campaign_id, match_type, role, min_matches, min(limit, 50))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
