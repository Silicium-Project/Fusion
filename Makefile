SHELL := /bin/bash

JOBS ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
MAKEFLAGS += -j$(JOBS)

DEMO_SUMMARY ?= splitter/run_output/demo/summary.json
DEMO_QUEUE ?= splitter/run_output/demo/queue.txt

.PHONY: all splitter executor worker demo demo-native demo-native-force run run-native run-binary test clean fclean re

all: splitter executor worker

splitter:
	$(MAKE) -C splitter all

executor:
	$(MAKE) -C executor all

worker: executor
	$(MAKE) -C worker all
demo: splitter executor
	$(MAKE) -C splitter demo

demo-native: splitter executor
	$(MAKE) -C splitter demo-native

demo-native-force: splitter executor
	$(MAKE) -C splitter demo-native-force

run: splitter executor
	$(MAKE) -C splitter run

run-native: splitter executor
	$(MAKE) -C splitter run-native

run-binary: splitter
	$(MAKE) -C splitter run-binary

demo-dynamo: splitter executor worker
	$(MAKE) -C splitter demo
	python3 -c 'from pathlib import Path; import json; summary = Path("$(DEMO_SUMMARY)"); queue = Path("$(DEMO_QUEUE)"); queue.parent.mkdir(parents=True, exist_ok=True); data = json.loads(summary.read_text()); ids = [part["id"] for part in data.get("partitions", [])]; queue.write_text("\n".join(ids) + ("\n" if ids else "")); print(f"Écrit {len(ids)} entrées dans {queue}")'
	@if command -v docker >/dev/null 2>&1; then \
		if docker info >/dev/null 2>&1; then \
		if docker build -t dynamorio-runner -f infra/docker/dynamorio-runner/Dockerfile .; then \
				:; \
			else \
				echo "Échec de docker build (ignoré)."; \
			fi; \
		else \
			echo "Docker indisponible, construction de l'image dynamorio-runner ignorée."; \
		fi; \
	else \
		echo "Docker introuvable, construction de l'image dynamorio-runner ignorée."; \
	fi
	./worker/worker \
		--summary $(DEMO_SUMMARY) \
		--queue $(DEMO_QUEUE) \
		--mode dynamo \
		--connector direct

test:
	$(MAKE) -C splitter test
	$(MAKE) -C executor test
	$(MAKE) -C worker test
	python3 -m pip install -r requirements-dev.txt
	python3 -m pytest

clean:
	$(MAKE) -C splitter clean
	$(MAKE) -C executor clean
	$(MAKE) -C worker clean

fclean:
	$(MAKE) -C splitter fclean
	$(MAKE) -C executor clean
	$(MAKE) -C worker clean
	@if command -v docker >/dev/null 2>&1; then \
		docker rmi -f \
			luis1454/worker:runtime \
			luis1454/worker:builder \
			luis1454/gui-runner:runtime \
			luis1454/gui-runner:builder \
			luis1454/gui-runner:headless \
			silicium/gui-runner:latest \
			silicium/gui-runner:builder \
			dynamorio-runner:latest \
			>/dev/null 2>&1 || true; \
	fi

re:
	$(MAKE) fclean
	$(MAKE) all
