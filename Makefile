.PHONY: harness-validate harness-test contract-test ingestion-test retrieval-test rag-test api-test evaluation-test evaluation-smoke sqlite-fts-fixture-smoke test

harness-validate:
	python3 scripts/validate_harness_contract.py

harness-test:
	python3 -m unittest discover -s tests/harness -p 'test_*.py' -v

contract-test:
	python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v

ingestion-test:
	python3 -m unittest discover -s tests/ingestion -p 'test_*.py' -v

retrieval-test:
	python3 -m unittest discover -s tests/retrieval -p 'test_*.py' -v

rag-test:
	python3 -m unittest discover -s tests/rag -p 'test_*.py' -v

api-test:
	python3 -m unittest discover -s tests/api -p 'test_*.py' -v

evaluation-test:
	python3 -m unittest discover -s tests/evaluation -p 'test_*.py' -v

evaluation-smoke:
	python3 -m backend.evaluation.harness --output runtime/evaluation/fixture-smoke-v1-report.json

sqlite-fts-fixture-smoke:
	python3 -m backend.retrieval.sqlite_fts build --chunks fixtures/chunks-v1.json --output runtime/evaluation/fixture-sqlite-fts-v1.sqlite
	python3 -m backend.evaluation.harness --cases evaluation/suites/fixture-sqlite-fts-v1.jsonl --chunks fixtures/chunks-v1.json --scope fixtures/authorized-scope-v1.json --suite-id fixture-sqlite-fts-v1 --retrieval-backend sqlite_fts5 --index runtime/evaluation/fixture-sqlite-fts-v1.sqlite --output runtime/evaluation/fixture-sqlite-fts-v1-report.json

test: harness-validate harness-test contract-test ingestion-test retrieval-test rag-test api-test evaluation-test
