"""Backend API (ADR-0004): thin HTTP layer over the ingestion workflow core.

POST /matches takes already-extracted screenshot data (`extracted_data`),
not an image - real screenshot upload -> score_extractor -> extracted_data
wiring is a separate, not-yet-built slice (ROADMAP Phase 1's "extraction
adapter" seam). Keeping this layer decoupled from the real vision call
mirrors how ingestion.workflow itself is tested.
"""

import os

import psycopg2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from ingestion.workflow import start_ingestion, submit_answer

load_dotenv()

app = FastAPI(title="Squadrons Backend")


def get_pg_conn():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        conn.close()


class StartMatchRequest(BaseModel):
    turn_id: str
    system_id: int
    match_type: str
    screenshot_ref: str
    extracted_data: dict


class AnswerRequest(BaseModel):
    answer: dict


@app.post("/matches")
def create_match(body: StartMatchRequest, pg_conn=Depends(get_pg_conn)):
    return start_ingestion(
        pg_conn,
        turn_id=body.turn_id,
        system_id=body.system_id,
        match_type=body.match_type,
        screenshot_ref=body.screenshot_ref,
        extracted_data=body.extracted_data,
    )


@app.post("/matches/{pending_match_id}/answer")
def answer_match(pending_match_id: int, body: AnswerRequest, pg_conn=Depends(get_pg_conn)):
    return submit_answer(pg_conn, pending_match_id, body.answer)
