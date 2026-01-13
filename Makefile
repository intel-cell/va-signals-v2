.PHONY: init test fr-ping

init:
	python3 -m venv .venv
	./.venv/bin/pip install -r requirements.txt

test:
	./.venv/bin/python -m pytest -q

fr-ping:
	./.venv/bin/python -m src.fetch_fr_ping
