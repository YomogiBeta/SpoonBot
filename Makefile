.PHONY: test
test:
	uv run python -m unittest discover -s tests -v

up:
	docker compose up -d

down:
	docker compose down