.PHONY: backend-test backend-coverage frontend-typecheck frontend-test verify

PYTHON ?= python
NPM ?= npm

backend-test:
	$(PYTHON) -m pytest -p no:cacheprovider tests/unit tests/eval -q

backend-coverage:
	$(PYTHON) -m pytest --cov=aim --cov-report=term-missing

frontend-typecheck:
	cd frontend && $(NPM) run typecheck

frontend-test:
	cd frontend && $(NPM) test -- --run

verify: backend-test frontend-typecheck frontend-test
