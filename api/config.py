import os

from dotenv import load_dotenv

load_dotenv()

# ROADMAP Phase 5: the static API key the campaign project must present
# (X-API-Key header) to call this backend's campaign-facing read endpoints.
# Distinct from ingestion/webhook.py's CAMPAIGN_WEBHOOK_SECRET, which is the
# key *this* backend presents to *them* on the outbound webhook call.
CAMPAIGN_API_KEY = os.environ["CAMPAIGN_API_KEY"]
