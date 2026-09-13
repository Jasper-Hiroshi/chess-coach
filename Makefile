.PHONY: dev test build up down

dev:
	python -m uvicorn app.main:app --reload --app-dir backend

test:
	python -m pytest backend/tests
	cd web && npm run build

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

