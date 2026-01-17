up:
	docker-compose up --build -d
down:
	docker-compose down -v

logs:
	docker-compose logs -f

shell:
	docker exec -it web bash

verify:
	docker-compose logs db | grep "running /docker-entrypoint-initdb.d/init.sql"

Test-connection:
	docker exec -it finance_db mysql -u user -psecretpassword -e "USE finance_db; SELECT * FROM servers;"
