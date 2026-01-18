.PHONY: up down logs shell verify Test-connection

help:
    @echo "Available commands:"
    @echo "  make up              - Start all services"
    @echo "  make down            - Stop and remove containers"
    @echo "  make logs            - View real-time logs"
    @echo "  make shell           - Open bash in web container"
    @echo "  make verify          - Verify database initialization"
    @echo "  make test-connection - Test MySQL connection"

up:
    docker-compose up --build -d --scale web=3

down:
    docker-compose down -v

logs:
    docker-compose logs -f

shell:
    docker exec -it interview-web-1 bash

verify:
    docker-compose logs db | grep "running /docker-entrypoint-initdb.d/init.sql"

test-connection:
    docker exec -it finance_db mysql -u user -psecretpassword -e "USE finance_db; SELECT * FROM servers;"

scale-up:
    docker-compose up -d --scale web=5

scale-down:
    docker-compose up -d --scale web=2

clean:
    docker system prune -f
    docker volume prune -f
