SHELL := /bin/sh

.PHONY: up down logs test lint format typecheck migrate run prod-up prod-down prod-logs reconcile

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f bot worker

prod-up:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f bot worker

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

reconcile:
	docker compose run --rm bot python -m app.scripts.reconcile_expenses
