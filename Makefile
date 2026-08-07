.PHONY: test smoke demo run docker

test:
	python3 -m unittest discover -s tests -v

smoke:
	./scripts/smoke-test.sh

demo:
	./scripts/demo-local.sh

run:
	PYTHONPATH=. python3 -m earn_or_halt run

docker:
	docker compose up --build
