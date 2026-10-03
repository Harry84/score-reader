# Testing quickstart

Steps to get the Discord score bot backend running locally for manual
testing. Say "do the steps in that file" (or "run everything needed for the
squadrons campaign project") and this is what should happen, in this order.

## 1. Start Postgres

```bash
docker compose up -d postgres
```

Wait for it to report healthy before continuing:

```bash
docker inspect --format='{{.State.Health.Status}}' screenshotreaderproject-postgres-1
```

## 2. Apply migrations

```bash
python -m db.run_migration
```

Safe to re-run — no-ops if the schema's already up to date.

## 3. Start the API backend

```bash
python -m uvicorn api.main:app --port 8001
```

Confirm it's up: `GET http://localhost:8001/docs` should return 200.

## 4. Start the bot

```bash
python -m bot.main
```

Confirm the log shows `Shard ID None has connected to Gateway`.

Neither the API nor the bot auto-reloads — restart both after editing code.

## Testing safety: which campaign does a report tag to?

By default the bot asks the separate campaign project's
`campaign_api_server` (`CAMPAIGN_API_URL`, default `http://localhost:8010`)
what's really pending and tags reports to that live campaign/turn/system.
That server is a different project and normally isn't running alongside
this checklist — when it's unreachable, the bot automatically falls back to
the hardcoded test defaults (`campaign_id="test-campaign"`,
`match_type="pickup"`) and says so in its reply, so ad-hoc testing is safe
by default.

If the live campaign server *does* happen to be running on your machine
while you're testing, force test isolation explicitly so a test screenshot
can't get tagged into real campaign data:

```
BOT_USE_TEST_CAMPAIGN=true
```

(set in `.env` or the shell before step 4).

## Cleanup after a test session

Test matches land in Postgres under `campaign_id = 'test-campaign'`, which
is a disjoint ELO scope from real match history (`campaign_id IS NULL`) —
see `[[bot-manual-test-isolation]]` — so nothing needs cleaning up for
safety, but delete the test rows anyway to keep the dev DB tidy:

```sql
DELETE FROM player_elo_history  WHERE campaign_id = 'test-campaign';
DELETE FROM player_elo_ratings  WHERE campaign_id = 'test-campaign';
DELETE FROM team_elo_history    WHERE campaign_id = 'test-campaign';
DELETE FROM team_elo_ratings    WHERE campaign_id = 'test-campaign';
DELETE FROM player_stats WHERE match_id IN (SELECT id FROM matches WHERE campaign_id = 'test-campaign');
DELETE FROM matches      WHERE campaign_id = 'test-campaign';
DELETE FROM pending_matches WHERE campaign_id = 'test-campaign';
```

Connect with:

```bash
docker exec -it screenshotreaderproject-postgres-1 psql -U squadrons -d squadrons
```
