"""Backend API (ADR-0004): thin HTTP layer over the ingestion workflow core.

POST /matches takes a real screenshot upload, runs it through score_extractor
(via the ingestion.extraction adapter), and feeds the result into the same
start_ingestion() used everywhere else.
"""

import os

import psycopg2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, UploadFile
from pydantic import BaseModel

from ingestion.extraction import extract_from_image_bytes
from ingestion.workflow import start_ingestion, submit_answer

load_dotenv()

app = FastAPI(title="Squadrons Backend")


def get_pg_conn():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        conn.close()


class AnswerRequest(BaseModel):
    answer: dict


@app.post("/matches")
async def create_match(
    turn_id: str = Form(...),
    system_id: int = Form(...),
    match_type: str = Form(...),
    screenshot_ref: str = Form(...),
    image: UploadFile = File(...),
    pg_conn=Depends(get_pg_conn),
):
    image_bytes = await image.read()
    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    extracted_data = extract_from_image_bytes(image_bytes, suffix=suffix)

    return start_ingestion(
        pg_conn,
        turn_id=turn_id,
        system_id=system_id,
        match_type=match_type,
        screenshot_ref=screenshot_ref,
        extracted_data=extracted_data,
    )


@app.post("/matches/{pending_match_id}/answer")
def answer_match(pending_match_id: int, body: AnswerRequest, pg_conn=Depends(get_pg_conn)):
    return submit_answer(pg_conn, pending_match_id, body.answer)
