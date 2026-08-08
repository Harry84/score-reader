import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")

# ROADMAP Phase 3: hardcoded to a single test channel for the MVP - the
# proper faction-channel scoping (ADR-0001) is Phase 4 polish.
BOT_CHANNEL_NAME = os.environ.get("BOT_CHANNEL_NAME", "ai-test")

# ADR-0008: admin-ness lives entirely in Discord's own role system, checked by
# the bot before it ever calls the backend - no backend-side admin concept.
# Default matches the role name used as an example in that ADR.
BOT_ADMIN_ROLE_NAME = os.environ.get("BOT_ADMIN_ROLE_NAME", "Bot Admin")

# Match context the score bot would normally infer from which
# command/channel triggered it, once the campaign project exists to supply
# it (ADR-0007). Crude/hardcoded for this phase per ROADMAP Phase 3.
# As of the live-campaign wiring below, these are now only the FALLBACK --
# used when BOT_USE_TEST_CAMPAIGN is set, or when the live campaign has
# nothing currently pending.
DEFAULT_CAMPAIGN_ID = os.environ.get("BOT_CAMPAIGN_ID", "test-campaign")
DEFAULT_TURN_ID = os.environ.get("BOT_TURN_ID", "test-turn")
DEFAULT_SYSTEM_ID = int(os.environ.get("BOT_SYSTEM_ID", "1"))  # Nadiri Dockyards
DEFAULT_MATCH_TYPE = os.environ.get("BOT_MATCH_TYPE", "pickup")

# Live-campaign wiring (Dynamic Trust Alignment project, a separate
# process): by default the bot asks that project's campaign_api_server
# which real campaign/turn/system a screenshot report is actually for
# (GET /api/pending_battles.json), instead of always tagging every report
# with the hardcoded defaults above -- see that project's window_engine.py,
# WindowEngine.get_pending_battle_context(). BOT_USE_TEST_CAMPAIGN is the
# explicit opt-out for testing: forces the old hardcoded-defaults behavior
# even with the campaign server up, so ad-hoc testing never needs a live
# campaign running and never risks tagging into real campaign data.
CAMPAIGN_API_URL = os.environ.get("CAMPAIGN_API_URL", "http://localhost:8010")
BOT_USE_TEST_CAMPAIGN = os.environ.get("BOT_USE_TEST_CAMPAIGN", "false").lower() == "true"
