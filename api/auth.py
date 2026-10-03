from fastapi import Header, HTTPException

from api import config


def require_campaign_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != config.CAMPAIGN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
