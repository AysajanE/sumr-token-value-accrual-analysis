# Data collection targets

.PHONY: registry snapshot index

registry:
	python -m src.registry.discover

snapshot:
	python -m src.indexing.defillama

index:
	python -m src.indexing.events
