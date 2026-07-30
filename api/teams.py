"""Team onboarding routes (ROADMAP Phase 2, ADR-0008).

POST /teams, POST /players, POST /teams/{id}/captain are Admin-only,
trusted implicitly from the caller - the score bot only exposes these
commands to Discord admins. POST /teams/{id}/roster is Captain-only and
independently verified against ref_teams.captain_discord_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_pg_conn
from teams.onboarding import (
    attach_player_to_roster,
    create_player,
    create_team,
    get_team,
    list_teams,
    set_captain,
)

router = APIRouter()


class CreateTeamRequest(BaseModel):
    name: str
    alias: str | None = None


class CreatePlayerRequest(BaseModel):
    name: str
    primary_team_id: int | None = None
    primary_role: str | None = None
    alias: str | None = None
    source_file: str | None = None


class SetCaptainRequest(BaseModel):
    captain_discord_id: str


class RosterRequest(BaseModel):
    requesting_discord_id: str
    ref_player_id: int


@router.post("/teams")
def create_team_route(body: CreateTeamRequest, pg_conn=Depends(get_pg_conn)):
    return create_team(pg_conn, body.name, alias=body.alias)


@router.get("/teams")
def list_teams_route(pg_conn=Depends(get_pg_conn)):
    return list_teams(pg_conn)


@router.get("/teams/{team_id}")
def get_team_route(team_id: int, pg_conn=Depends(get_pg_conn)):
    try:
        return get_team(pg_conn, team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/players")
def create_player_route(body: CreatePlayerRequest, pg_conn=Depends(get_pg_conn)):
    return create_player(
        pg_conn,
        body.name,
        primary_team_id=body.primary_team_id,
        primary_role=body.primary_role,
        alias=body.alias,
        source_file=body.source_file,
    )


@router.post("/teams/{team_id}/captain")
def set_captain_route(team_id: int, body: SetCaptainRequest, pg_conn=Depends(get_pg_conn)):
    try:
        return set_captain(pg_conn, team_id, body.captain_discord_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/teams/{team_id}/roster")
def attach_player_to_roster_route(team_id: int, body: RosterRequest, pg_conn=Depends(get_pg_conn)):
    try:
        attach_player_to_roster(pg_conn, team_id, body.requesting_discord_id, body.ref_player_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "attached"}
