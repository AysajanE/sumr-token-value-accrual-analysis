.PHONY: help registry snapshot index analyze evidence v2_workflow monitor_cycle refresh_claims refresh_lvusdc_nav freeze_baseline baseline_status report comprehensive_report investor_extended investor_pack investor_latex investor_pdf clean all

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

all: registry snapshot index analyze report ## Run full pipeline

# ---------- Data Collection ----------

registry: ## Step 1: Build/update contract registry
	python -m src.registry.discover

snapshot: ## Pull DeFiLlama API snapshots (TVL, fees, revenue)
	python -m src.indexing.defillama

index: ## Index on-chain events (transfers, tips, staking, rewards)
	python -m src.indexing.events

# ---------- Analysis ----------

analyze: ## Compute KPIs, scenarios, and benchmarks
	python -m src.analysis.metrics
	python -m src.analysis.scenarios

EVIDENCE_SNAPSHOT_DIR ?= data/snapshots/external_review/2026-02-09-independent
EVIDENCE_OUTPUT_DIR ?= results/proofs/evidence_2026-02-09-independent

evidence: ## Build deterministic evidence tables from frozen snapshots
	python -m src.analysis.evidence --snapshot-dir '$(EVIDENCE_SNAPSHOT_DIR)' --output-dir '$(EVIDENCE_OUTPUT_DIR)'

V2_EVIDENCE_DIR ?= results/proofs/evidence_2026-02-09-independent
V2_TABLES_DIR ?= results/tables
V2_CHARTS_DIR ?= results/charts

v2_workflow: ## Build ticket closure workflow, gate-passed KPI tables/charts, and gate-validated scenarios
	python -m src.analysis.v2_workflow --evidence-dir '$(V2_EVIDENCE_DIR)' --tables-dir '$(V2_TABLES_DIR)' --charts-dir '$(V2_CHARTS_DIR)'

monitor_cycle: ## Run refresh+evidence+workflow and append monitoring snapshot row
	$(MAKE) refresh_claims
	$(MAKE) refresh_lvusdc_nav
	$(MAKE) evidence
	$(MAKE) v2_workflow
	python -m src.analysis.monitor_cycle --snapshot-dir '$(REFRESH_SNAPSHOT_DIR)' --evidence-dir '$(EVIDENCE_OUTPUT_DIR)' --tables-dir '$(V2_TABLES_DIR)'

REFRESH_SNAPSHOT_DIR ?= data/snapshots/external_review/2026-02-09-independent
REFRESH_FROM_BLOCK ?= 41932733
REFRESH_CHUNK_SIZE ?= 10000
REFRESH_RPC_URL ?= https://base.drpc.org

refresh_claims: ## Refresh post-exec distributor claim snapshots + receipt proofs + hash manifest
	python -m src.indexing.claims_refresh --snapshot-dir '$(REFRESH_SNAPSHOT_DIR)' --from-block $(REFRESH_FROM_BLOCK) --chunk-size $(REFRESH_CHUNK_SIZE) --rpc-url '$(REFRESH_RPC_URL)'

refresh_lvusdc_nav: ## Refresh LVUSDC convertToAssets snapshots at relevant blocks
	python -m src.indexing.lvusdc_nav_refresh --snapshot-dir '$(REFRESH_SNAPSHOT_DIR)' --from-block $(REFRESH_FROM_BLOCK) --rpc-url '$(REFRESH_RPC_URL)'

reconcile: ## Run cross-source reconciliation checks
	python -m src.reconciliation.checks

# ---------- Reporting ----------

report: ## Generate final validation report set (short + comprehensive)
	python -m src.analysis.report_sync
	python -m src.analysis.comprehensive_report
	python -m src.analysis.investor_extended
	python -m src.analysis.investor_pack
	python -m src.analysis.investor_latex

comprehensive_report: ## Generate comprehensive value accrual report
	python -m src.analysis.comprehensive_report

investor_pack: ## Generate investor-facing executive summary and visualizations
	python -m src.analysis.investor_pack

investor_extended: ## Build extended investor artifacts (benchmarks, macro, treasury, staking, probability-weighted PnL)
	python -m src.analysis.investor_extended

investor_latex: ## Generate investor-facing LaTeX from latest artifacts
	python -m src.analysis.investor_latex

investor_pdf: ## Generate investor-facing PDF (requires LaTeX engine)
	python -m src.analysis.investor_latex --compile

freeze_baseline: ## Freeze checksum baseline manifest for current results artifacts
	python -m src.analysis.baseline_freeze --results-dir 'results' --tables-dir 'results/tables' --monitoring-path 'results/tables/monitoring_latest.json'

baseline_status: ## Show latest baseline manifest date and refresh block range
	python -m src.analysis.baseline_freeze --tables-dir 'results/tables' --show-latest

# ---------- Utilities ----------

clean: ## Remove generated data and results
	rm -rf data/indexed/* data/prices/* data/snapshots/defillama/*.json data/snapshots/explorer/*.json
	rm -rf results/charts/* results/tables/*
	@echo "Cleaned generated files. Registry and ABIs preserved."
