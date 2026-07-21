.PHONY: contract-test ingestion-test retrieval-test rag-test api-test evaluation-test evaluation-smoke test

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

test: contract-test ingestion-test retrieval-test rag-test api-test evaluation-test
