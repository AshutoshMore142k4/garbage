.PHONY: setup ingest gen close bench redteam demo test

PYTHON ?= python3
SEED ?= 42

setup:
	$(PYTHON) -m pip install -e ".[dev]"

ingest:
	$(PYTHON) -m ledgerguard.razorpay.ingest

gen:
	$(PYTHON) -m data.generator --seed $(SEED) --out data/raw

close:
	@echo "close: not yet implemented (see phases.md Phase 3-6)"

bench:
	@echo "bench: not yet implemented (see phases.md Phase 9)"

redteam:
	@echo "redteam: not yet implemented (see phases.md Phase 7)"

demo:
	@echo "demo: not yet implemented (see phases.md Phase 10)"

test:
	$(PYTHON) -m pytest -q
