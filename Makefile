HOSTS_FILE=hosts.json

default: up

up: hosts_file
	docker-compose up

down:
	docker-compose down -v

hosts_file:
	touch $(HOSTS_FILE)
