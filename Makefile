SHELL := /bin/bash

DEMO_SUMMARY ?= tools/experiments/splitter/demo/output/summary.json
DEMO_QUEUE ?= tools/experiments/splitter/demo/output/queue.txt

.PHONY: all splitter executor worker demo demo-native demo-native-force run run-native run-binary test clean fclean re

all: splitter executor worker

splitter:
	$(MAKE) -C tools/experiments/splitter all

executor:
	$(MAKE) -C tools/experiments/fragment-executor all

worker:
	$(MAKE) -C tools/worker all
demo: splitter executor
	$(MAKE) -C tools/experiments/splitter demo

demo-native: splitter executor
	$(MAKE) -C tools/experiments/splitter demo-native

demo-native-force: splitter executor
	$(MAKE) -C tools/experiments/splitter demo-native-force

run: splitter executor
	$(MAKE) -C tools/experiments/splitter run

run-native: splitter executor
	$(MAKE) -C tools/experiments/splitter run-native

run-binary: splitter
	$(MAKE) -C tools/experiments/splitter run-binary

demo-dynamo: splitter executor worker
	$(MAKE) -C tools/experiments/splitter demo
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
	./tools/worker/worker \
		--summary $(DEMO_SUMMARY) \
		--queue $(DEMO_QUEUE) \
		--backend dynamo \
		--connector direct

test:
	$(MAKE) -C tools/experiments/splitter test
	$(MAKE) -C tools/experiments/fragment-executor test
	$(MAKE) -C tools/worker test
	python3 -m pip install -r requirements-dev.txt
	python3 -m pytest

clean:
	$(MAKE) -C tools/experiments/splitter clean
	$(MAKE) -C tools/experiments/fragment-executor clean
	$(MAKE) -C tools/worker clean

fclean:
	$(MAKE) -C tools/experiments/splitter fclean
	$(MAKE) -C tools/experiments/fragment-executor clean
	$(MAKE) -C tools/worker clean

re:
	$(MAKE) fclean
	$(MAKE) all
