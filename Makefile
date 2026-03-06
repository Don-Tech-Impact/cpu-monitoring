.PHONY: up down logs shell verify test-connection test test-cov help scale-up scale-down clean env-check

help:
	@echo "Available commands:"
	@echo "  make up              - Start all services (3 web instances)"
	@echo "  make down            - Stop and remove containers"
	@echo "  make logs            - View real-time logs"
	@echo "  make shell           - Open bash in web container"
	@echo "  make verify          - Verify database initialization"
	@echo "  make test-connection - Test MySQL connection"
	@echo "  make test            - Run test suite (inside Docker)"
	@echo "  make test-cov        - Run tests with coverage report"
	@echo "  make scale-up        - Scale to 5 web instances"
	@echo "  make scale-down      - Scale to 2 web instances"
	@echo "  make clean           - Clean up Docker resources"
	@echo "  make env-check       - Validate .env file exists"

env-check:
	@test -f .env || (echo "ERROR: .env file not found. Run: cp config/.env.example .env" && exit 1)
	@echo ".env file found."

up: env-check
	docker compose up --build -d --scale web=3

down:
	docker compose down -v

logs:
	docker compose logs -f

shell:
	docker compose exec web bash

verify:
	docker compose logs db | grep "running /docker-entrypoint-initdb.d/init.sql"

test-connection:
	docker compose exec db mysqladmin ping -h localhost -u root -p$${MYSQL_ROOT_PASSWORD:-changeme_root}

test:
	docker compose exec web python -m pytest tests/ -v --tb=short

test-cov:
	docker compose exec web python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

scale-up:
	docker compose up -d --scale web=5

scale-down:
	docker compose up -d --scale web=2

clean:
	docker system prune -f
	docker volume prune -f

