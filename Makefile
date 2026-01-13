.PHONY: init test fr-ping

init:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	. .venv/bin/activate && pytest -q

fr-ping:
	. .venv/bin/activate && python -m src.fetch_fr_ping
