# Analysis targets

.PHONY: analyze reconcile

analyze:
	python -m src.analysis.metrics
	python -m src.analysis.scenarios

reconcile:
	python -m src.reconciliation.checks
