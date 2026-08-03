import httpx

from ingestion import webhook


def test_no_op_when_webhook_url_unset(monkeypatch):
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_URL", None)
    calls = []
    monkeypatch.setattr(webhook, "_post", lambda *a, **k: calls.append((a, k)))

    webhook.send_match_persisted({"match_id": 1})

    assert calls == []


def test_sends_payload_with_secret_header(monkeypatch):
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_URL", "http://campaign.example/hook")
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_SECRET", "shh")
    calls = []
    monkeypatch.setattr(
        webhook, "_post", lambda url, json, headers: calls.append((url, json, headers))
    )

    summary = {"match_id": 42, "winner": "IMPERIAL"}
    webhook.send_match_persisted(summary)

    assert calls == [("http://campaign.example/hook", summary, {"X-API-Key": "shh"})]


def test_no_header_when_secret_unset(monkeypatch):
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_URL", "http://campaign.example/hook")
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_SECRET", None)
    calls = []
    monkeypatch.setattr(webhook, "_post", lambda url, json, headers: calls.append(headers))

    webhook.send_match_persisted({"match_id": 1})

    assert calls == [{}]


def test_retries_then_gives_up_without_raising(monkeypatch):
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_URL", "http://campaign.example/hook")
    monkeypatch.setattr(webhook, "RETRY_DELAY", 0)
    attempts = []

    def _always_fails(url, json, headers):
        attempts.append(1)
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(webhook, "_post", _always_fails)

    webhook.send_match_persisted({"match_id": 1})  # must not raise

    assert len(attempts) == webhook.MAX_RETRIES


def test_succeeds_after_transient_failure(monkeypatch):
    monkeypatch.setattr(webhook, "CAMPAIGN_WEBHOOK_URL", "http://campaign.example/hook")
    monkeypatch.setattr(webhook, "RETRY_DELAY", 0)
    attempts = []

    def _fails_once_then_succeeds(url, json, headers):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(webhook, "_post", _fails_once_then_succeeds)

    webhook.send_match_persisted({"match_id": 1})

    assert len(attempts) == 2
