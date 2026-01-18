.PHONY: up down logs shell verify test-connection help scale-up scale-down clean

help:
→ TAB HERE @echo "Available commands:"
→ TAB HERE @echo "  make up              - Start all services"
→ TAB HERE @echo "  make down            - Stop and remove containers"
→ TAB HERE @echo "  make logs            - View real-time logs"
→ TAB HERE @echo "  make shell           - Open bash in web container"
→ TAB HERE @echo "  make verify          - Verify database initialization"
→ TAB HERE @echo "  make test-connection - Test MySQL connection"
→ TAB HERE @echo "  make scale-up        - Scale to 5 instances"
→ TAB HERE @echo "  make scale-down      - Scale to 2 instances"
→ TAB HERE @echo "  make clean           - Clean up Docker resources"

up:
→ TAB HERE docker-compose up --build -d --scale web=3

down:
→ TAB HERE docker-compose down -v

logs:
→ TAB HERE docker-compose logs -f

shell:
→ TAB HERE docker exec -it interview-web-1 bash

verify:
→ TAB HERE docker-compose logs db | grep "running /docker-entrypoint-initdb.d/init.sql"

test-connection:
→ TAB HERE docker exec -it finance_db mysql -u user -psecretpassword -e "USE finance_db; SELECT * FROM servers;"

scale-up:
→ TAB HERE docker-compose up -d --scale web=5

scale-down:
→ TAB HERE docker-compose up -d --scale web=2

clean:
→ TAB HERE docker system prune -f
→ TAB HERE docker volume prune -f

