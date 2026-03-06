SHELL := /bin/bash

.PHONY: help
help:
	@echo "Targets:"
	@echo "  backend-dev   - run backend with reload"
	@echo "  backend-test  - run backend tests"
	@echo "  backend-fmt   - format backend (ruff)"
	@echo "  backend-lint  - lint backend (ruff)"
	@echo "  frontend-dev  - run Next.js frontend"
	@echo "  frontend-test - lint + typecheck + build frontend"
	@echo "  frontend-lint - lint frontend"
	@echo "  frontend-typecheck - type-check frontend"
	@echo "  docker-test   - run optional docker-marked backend tests"

.PHONY: backend-dev
backend-dev:
	cd backend && uvicorn howlhouse.api.main:app --reload --port 8000

.PHONY: backend-test
backend-test:
	cd backend && pytest -q

.PHONY: backend-fmt
backend-fmt:
	cd backend && ruff format .

.PHONY: backend-lint
backend-lint:
	cd backend && ruff check .

.PHONY: frontend-dev
frontend-dev:
	cd frontend && npm run dev

.PHONY: frontend-test
frontend-test:
	cd frontend && npm run lint && npm run typecheck && npm run build

.PHONY: frontend-lint
frontend-lint:
	cd frontend && npm run lint

.PHONY: frontend-typecheck
frontend-typecheck:
	cd frontend && npm run typecheck

.PHONY: docker-test
docker-test:
	cd backend && pytest -q -m docker
