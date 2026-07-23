ifeq ($(OS),Windows_NT)
PROJECT_PYTHON := .venv/Scripts/python.exe
else
PROJECT_PYTHON := .venv/bin/python
endif

ifeq ($(wildcard $(PROJECT_PYTHON)),)
$(error Project virtualenv is missing at $(PROJECT_PYTHON); create .venv and install the project dependencies first)
endif

.PHONY: harness-validate powershell-check harness-test contract-test storage-test ingestion-test retrieval-test rag-test api-test evaluation-test validation-test stage1-local-canary real-generation-canary phase2-model-selection fixed-reranker-test fixed-reranker-gate evaluation-contract-check formal-evaluation-fixture evaluation-smoke sqlite-fts-fixture-smoke vector-fixture-smoke rrf-fixture-smoke test

harness-validate:
	$(PROJECT_PYTHON) scripts/validate_harness_contract.py

powershell-check:
	pwsh -NoLogo -NoProfile -NonInteractive -File scripts/check_powershell.ps1

harness-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/harness -p 'test_*.py' -v

contract-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/contracts -p 'test_*.py' -v

storage-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/storage -p 'test_*.py' -v

ingestion-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/ingestion -p 'test_*.py' -v

retrieval-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/retrieval -p 'test_*.py' -v

rag-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/rag -p 'test_*.py' -v

api-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/api -p 'test_*.py' -v

evaluation-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/evaluation -p 'test_*.py' -v

validation-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/validation -p 'test_*.py' -v

stage1-local-canary:
	$(PROJECT_PYTHON) -m unittest -v \
		tests.storage.test_pdf_object_store \
		tests.storage.test_postgres_fact_source \
		tests.ingestion.test_persistent_ingestion \
		tests.ingestion.test_index_lifecycle \
		tests.ingestion.test_elasticsearch_version_writer \
		tests.ingestion.test_milvus_version_writer \
		tests.ingestion.test_cleanup \
		tests.retrieval.test_online_visibility \
		tests.api.test_online_ready_rag_answers_api \
		tests.validation.test_stage1_reconciliation

real-generation-canary:
	$(PROJECT_PYTHON) scripts/run_local_real_generation_canary.py

phase2-model-selection:
	$(PROJECT_PYTHON) scripts/run_phase2_model_selection.py

fixed-reranker-test:
	$(PROJECT_PYTHON) -m unittest -v tests.evaluation.test_fixed_reranker

fixed-reranker-gate:
	$(PROJECT_PYTHON) scripts/run_fixed_reranker_gate.py \
		--manifest runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/manifest.json \
		--chunks runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json \
		--candidates runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/rankings-v1/local_rrf.jsonl \
		--document-catalog fixtures/sample-corpus-v1.json \
		--output-dir runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/reranker-bge-v2-m3-v1

evaluation-contract-check:
	$(PROJECT_PYTHON) scripts/export_evaluation_contracts.py --check

formal-evaluation-fixture:
	$(PROJECT_PYTHON) -m backend.evaluation.formal_corpus --manifest evaluation/formal/fixture-manifest-v1.json --output runtime/evaluation/formal-fixture-validation-v1.json
	$(PROJECT_PYTHON) -m backend.evaluation.retrieval_metrics --manifest evaluation/formal/fixture-manifest-v1.json --run lexical_overlap=evaluation/formal/fixture-rankings-lexical-v1.jsonl --run local_rrf=evaluation/formal/fixture-rankings-rrf-v1.jsonl --split dev --k 3 --output runtime/evaluation/formal-fixture-metrics-v1.json

evaluation-smoke:
	$(PROJECT_PYTHON) -m backend.evaluation.harness --output runtime/evaluation/fixture-smoke-v1-report.json

sqlite-fts-fixture-smoke:
	$(PROJECT_PYTHON) -m backend.retrieval.sqlite_fts build --chunks fixtures/chunks-v1.json --output runtime/evaluation/fixture-sqlite-fts-v1.sqlite
	$(PROJECT_PYTHON) -m backend.evaluation.harness --cases evaluation/suites/fixture-sqlite-fts-v1.jsonl --chunks fixtures/chunks-v1.json --scope fixtures/authorized-scope-v1.json --suite-id fixture-sqlite-fts-v1 --retrieval-backend sqlite_fts5 --index runtime/evaluation/fixture-sqlite-fts-v1.sqlite --output runtime/evaluation/fixture-sqlite-fts-v1-report.json

vector-fixture-smoke:
	$(PROJECT_PYTHON) -m backend.retrieval.vector build --chunks fixtures/chunks-v1.json --output runtime/evaluation/fixture-vector-v1.sqlite
	$(PROJECT_PYTHON) -m backend.evaluation.harness --cases evaluation/suites/fixture-vector-v1.jsonl --chunks fixtures/chunks-v1.json --scope fixtures/authorized-scope-v1.json --suite-id fixture-vector-v1 --retrieval-backend local_vector --vector-index runtime/evaluation/fixture-vector-v1.sqlite --output runtime/evaluation/fixture-vector-v1-report.json

rrf-fixture-smoke:
	$(PROJECT_PYTHON) -m backend.retrieval.sqlite_fts build --chunks fixtures/chunks-v1.json --output runtime/evaluation/fixture-rrf-v1.fts.sqlite
	$(PROJECT_PYTHON) -m backend.retrieval.vector build --chunks fixtures/chunks-v1.json --output runtime/evaluation/fixture-rrf-v1.vector.sqlite
	$(PROJECT_PYTHON) -m backend.evaluation.harness --cases evaluation/suites/fixture-rrf-v1.jsonl --chunks fixtures/chunks-v1.json --scope fixtures/authorized-scope-v1.json --suite-id fixture-rrf-v1 --retrieval-backend local_rrf --index runtime/evaluation/fixture-rrf-v1.fts.sqlite --vector-index runtime/evaluation/fixture-rrf-v1.vector.sqlite --output runtime/evaluation/fixture-rrf-v1-report.json

test: harness-validate harness-test contract-test storage-test ingestion-test retrieval-test rag-test api-test evaluation-test validation-test evaluation-contract-check
