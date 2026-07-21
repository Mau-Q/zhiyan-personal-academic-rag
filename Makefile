.PHONY: contract-test

contract-test:
	python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
