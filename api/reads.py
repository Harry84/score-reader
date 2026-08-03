"""Campaign-project read routes (ROADMAP Phase 5, ADR-0001): the narrative
bot only ever reads Match/Team/stats data from this project, never writes -
all routes here are gated behind require_campaign_api_key.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_campaign_api_key
from api.dependencies import get_pg_conn
from ingestion.workflow import get_latest_match
from stats.player_elo import GENERAL as PLAYER_ELO_GENERAL
from stats.player_elo import get_player_elo_ladder
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
