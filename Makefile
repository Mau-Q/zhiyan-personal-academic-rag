.PHONY: contract-test retrieval-test rag-test api-test test

contract-test:
	python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v

retrieval-test:
	python3 -m unittest discover -s tests/retrieval -p 'test_*.py' -v

rag-test:
	python3 -m unittest discover -s tests/rag -p 'test_*.py' -v

api-test:
	python3 -m unittest discover -s tests/api -p 'test_*.py' -v

test: contract-test retrieval-test rag-test api-test
