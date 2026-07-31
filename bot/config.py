import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")

# ROADMAP Phase 3: hardcoded to a single test channel for the MVP - the
# proper faction-channel scoping (ADR-0001) is Phase 4 polish.
BOT_CHANNEL_NAME = os.environ.get("BOT_CHANNEL_NAME", "ai-test")

# Match context the score bot would normally infer from which
# command/channel triggered it, once the campaign project exists to supply
# it (ADR-0007). Crude/hardcoded for this phase per ROADMAP Phase 3.
DEFAULT_CAMPAIGN_ID = os.environ.get("BOT_CAMPAIGN_ID", "test-campaign")
DEFAULT_TURN_ID = os.environ.get("BOT_TURN_ID", "test-turn")
DEFAULT_SYSTEM_ID = int(os.environ.get("BOT_SYSTEM_ID", "1"))  # Nadiri Dockyards
DEFAULT_MATCH_TYPE = os.environ.get("BOT_MATCH_TYPE", "pickup")
