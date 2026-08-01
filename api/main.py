"""Backend API (ADR-0004): thin HTTP layer over the ingestion workflow core.

POST /matches takes a real screenshot upload, runs it through score_extractor
(via the ingestion.extraction adapter), and feeds the result into the same
start_ingestion() used everywhere else.
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from api.dependencies import get_pg_conn
from api.teams import router as teams_router
from ingestion.extraction import extract_from_image_bytes
from ingestion.workflow import (
    DuplicateMatchError,
    cancel_ingestion,
    check_duplicate_image,
    edit_match_player,
    edit_match_winner,
    start_ingestion,
    submit_answer,
)

load_dotenv()

app = FastAPI(title="Squadrons Backend")
app.include_router(teams_router)


class AnswerRequest(BaseModel):
    answer: dict


class EditPlayerRequest(BaseModel):
    updates: dict


class EditWinnerRequest(BaseModel):
    winner: str


def _duplicate_match_exception(e):
    return HTTPException(
        status_code=409,
        detail={"message": str(e), "existing_match": e.existing_summary},
    )


@app.post("/matches")
async def create_match(
    campaign_id: str = Form(...),
    turn_id: str = Form(...),
    system_id: int = Form(...),
    match_type: str = Form(...),
    screenshot_ref: str = Form(...),
    image: UploadFile = File(...),
    pg_conn=Depends(get_pg_conn),
):
    image_bytes = await image.read()
    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"

    try:
        image_hash = check_duplicate_image(pg_conn, campaign_id, image_bytes)
    except DuplicateMatchError as e:
        raise _duplicate_match_exception(e)

    extracted_data = extract_from_image_bytes(image_bytes, suffix=suffix)

    try:
        return start_ingestion(
            pg_conn,
            campaign_id=campaign_id,
            turn_id=turn_id,
            system_id=system_id,
            match_type=match_type,
            screenshot_ref=screenshot_ref,
            extracted_data=extracted_data,
            image_hash=image_hash,
        )
    except DuplicateMatchError as e:
        raise _duplicate_match_exception(e)


@app.post("/matches/{pending_match_id}/answer")
def answer_match(pending_match_id: int, body: AnswerRequest, pg_conn=Depends(get_pg_conn)):
    return submit_answer(pg_conn, pending_match_id, body.answer)


@app.post("/matches/{pending_match_id}/cancel")
def cancel_match_route(pending_match_id: int, pg_conn=Depends(get_pg_conn)):
    try:
        return cancel_ingestion(pg_conn, pending_match_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch("/matches/{match_id}/players/{player_name}")
def edit_match_player_route(
    match_id: int, player_name: str, body: EditPlayerRequest, pg_conn=Depends(get_pg_conn)
):
    try:
        return edit_match_player(pg_conn, match_id, player_name, body.updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch("/matches/{match_id}/winner")
def edit_match_winner_route(match_id: int, body: EditWinnerRequest, pg_conn=Depends(get_pg_conn)):
    try:
        return edit_match_winner(pg_conn, match_id, body.winner)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
