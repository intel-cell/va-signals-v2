.PHONY: init test fr-ping db-init fr-delta ecfr-delta dashboard report-daily report-weekly summarize fetch-transcripts embed agenda-drift bills

init:
	python3 -m venv .venv
	./.venv/bin/pip install -r requirements.txt

test:
	./.venv/bin/python -m pytest -q

fr-ping:
	./.venv/bin/python -m src.fetch_fr_ping

db-init:
	./.venv/bin/python -c "from src.db import init_db, assert_tables_exist; init_db(); assert_tables_exist()"

fr-delta:
	./.venv/bin/python -m src.run_fr_delta

ecfr-delta:
	./.venv/bin/python -m src.run_ecfr_delta

dashboard:
	./.venv/bin/uvicorn src.dashboard_api:app --reload --port 8000

report-daily:
	./.venv/bin/python -m src.reports daily

report-weekly:
	./.venv/bin/python -m src.reports weekly

summarize:
	ANTHROPIC_API_KEY=$$(security find-generic-password -s "claude-api" -a "$$USER" -w) ./.venv/bin/python -m src.summarize --pending

fetch-transcripts:
	CONGRESS_API_KEY=$$(security find-generic-password -s "congress-api" -a "$$USER" -w) ./.venv/bin/python -m src.fetch_transcripts --limit 10

embed:
	./.venv/bin/python -m src.embed_utterances

agenda-drift:
	./.venv/bin/python -m src.run_agenda_drift --all

bills:
	./.venv/bin/python -m src.run_bills
