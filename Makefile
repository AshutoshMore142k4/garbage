.PHONY: setup ingest gen close bench redteam d1 demo test

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
	@echo "demo: not yet implemented (see phases.md Phase 10)"

test:
	$(PYTHON) -m pytest -q
