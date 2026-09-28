SHELL := /bin/bash

PYTHON ?= python3

.PHONY: all test check lint golden smoke raytracer-test rust-test rust-lint clean re

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
	cargo test -p silicium-raytracer

rust-test:
	cargo test --workspace --locked

rust-lint:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings

clean:
	$(PYTHON) ./silicium clean cache

re: clean all
