SHELL := /bin/sh

.PHONY: up down logs test lint format typecheck migrate run

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f bot worker

run:
	python -m app.main

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy app tests

migrate:
	alembic upgrade head

