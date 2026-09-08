SHELL := /bin/bash

PYTHON ?= python3
RAYTRACER_MANIFEST := workloads/raytracer/native/Cargo.toml

.PHONY: all test check lint golden smoke raytracer-test clean re

all: check

test:
	$(PYTHON) -m pytest

check:
	CORE_CHECK_MODE=quick CORE_CHECK_SCOPE=platform bash ci/core_check.sh

lint:
	$(PYTHON) ./silicium workload lint

golden:
	$(PYTHON) ./silicium workload golden --strict

smoke:
	$(PYTHON) ./silicium smoke

raytracer-test:
	cargo test --manifest-path $(RAYTRACER_MANIFEST)

clean:
	$(PYTHON) ./silicium clean cache

re: clean all
