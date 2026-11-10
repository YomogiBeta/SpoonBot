.PHONY: test
test:
	uv run python -m unittest discover -s tests -v

check:
	uv run ruff check .
	uv run pyright

up:
	docker compose up -d

down:
	docker compose down