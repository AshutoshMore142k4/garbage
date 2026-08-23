.PHONY: setup ingest gen close bench redteam d1 demo test snapshot api ui

PYTHON ?= python3
SEED ?= 42

setup:
	$(PYTHON) -m pip install -e ".[dev]"

ingest:
	$(PYTHON) -m ledgerguard.razorpay.ingest

gen:
	$(PYTHON) -m data.generator --seed $(SEED) --out data/raw

close:
	$(PYTHON) -m ledgerguard.close --data-dir data/raw --db-path ledgerguard.db --audit-path audit.jsonl

bench:
	$(PYTHON) -m benchmark.ablation
	$(PYTHON) -m eval.metrics

redteam:
	$(PYTHON) -m eval.redteam_eval

d1:
	$(PYTHON) -m eval.rule_learning

demo:
	$(PYTHON) -m ledgerguard.demo

snapshot:
	$(PYTHON) -m eval.snapshot

# The API the deployed UI runs against. Serves the real pipeline over the committed sample data.
api:
	$(PYTHON) -m uvicorn ledgerguard.api.app:app --reload --port 8000

# The frontend dev server. Expects `make api` in another shell; falls back to the committed
# snapshot when the backend isn't up, so it is usable either way.
ui:
	cd frontend && npm install && npm run dev

test:
	$(PYTHON) -m pytest -q
