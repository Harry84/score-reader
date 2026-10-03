"""Outbound push to the campaign project once a Match persists (ROADMAP
Phase 5, ADR-0001): "this backend owns the config/credentials for calling
the other project's webhook endpoint."

Deliberately synchronous (httpx.Client, not AsyncClient): _persist in
ingestion/workflow.py is plain psycopg2 with no async/await anywhere, and is
reached from both an async route (POST /matches) and a sync one
(POST /matches/{id}/answer) - asyncio.run() would work from the sync route
but crash from the already-running event loop under the async one. A sync
client sidesteps that inconsistency entirely.

Best-effort: a delivery failure must never fail the Match persist itself
(that's what actually matters - the campaign project can always poll GET
/matches/latest as a fallback). Retries a bounded number of times, then
logs and gives up - modeled on score_extractor's retry loop (fixed delay,
not exponential backoff).
"""

import logging
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

# Unset by default - the campaign project has no receiver yet (ROADMAP).
# send_match_persisted no-ops until this is configured.
CAMPAIGN_WEBHOOK_URL = os.environ.get("CAMPAIGN_WEBHOOK_URL")

# The key *this* backend presents to *them* - distinct from
# api/config.py's CAMPAIGN_API_KEY, which is the key *they* present to *us*.
CAMPAIGN_WEBHOOK_SECRET = os.environ.get("CAMPAIGN_WEBHOOK_SECRET")

MAX_RETRIES = 3
RETRY_DELAY = 5

logger = logging.getLogger(__name__)


def _post(url, json, headers):
    """The actual HTTP call, isolated so tests can monkeypatch just this
    seam instead of mocking httpx.Client internals."""
    response = httpx.Client(timeout=10).post(url, json=json, headers=headers)
    response.raise_for_status()


def send_match_persisted(summary):
    if not CAMPAIGN_WEBHOOK_URL:
        return

    headers = {"X-API-Key": CAMPAIGN_WEBHOOK_SECRET} if CAMPAIGN_WEBHOOK_SECRET else {}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _post(CAMPAIGN_WEBHOOK_URL, summary, headers)
            return
        except httpx.HTTPError as e:
            logger.error(
                "Webhook delivery attempt %d/%d failed for match %s: %s",
                attempt,
                MAX_RETRIES,
                summary.get("match_id"),
                e,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.error(
        "Webhook delivery failed after %d attempts; match %s persisted but "
        "campaign project was not notified",
        MAX_RETRIES,
        summary.get("match_id"),
    )
