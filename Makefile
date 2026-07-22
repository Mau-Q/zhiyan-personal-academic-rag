ifeq ($(OS),Windows_NT)
PROJECT_PYTHON := .venv/Scripts/python.exe
else
PROJECT_PYTHON := .venv/bin/python
endif

ifeq ($(wildcard $(PROJECT_PYTHON)),)
$(error Project virtualenv is missing at $(PROJECT_PYTHON); create .venv and install the project dependencies first)
endif

.PHONY: harness-validate harness-test contract-test ingestion-test retrieval-test rag-test api-test evaluation-test evaluation-contract-check formal-evaluation-fixture evaluation-smoke sqlite-fts-fixture-smoke vector-fixture-smoke rrf-fixture-smoke test

harness-validate:
	$(PROJECT_PYTHON) scripts/validate_harness_contract.py

harness-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/harness -p 'test_*.py' -v

contract-test:
	$(PROJECT_PYTHON) -m unittest discover -s tests/contracts -p 'test_*.py' -v

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

test: harness-validate harness-test contract-test ingestion-test retrieval-test rag-test api-test evaluation-test evaluation-contract-check
