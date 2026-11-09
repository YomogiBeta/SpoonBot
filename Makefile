PYTHON ?= .venv/bin/python

.PHONY: test
test:
	$(PYTHON) -m unittest discover -s tests -v

up:
	docker compose up -d

down:
	docker compose down