SHELL := /bin/bash

PYTHON ?= python3

.PHONY: all check test e2e smoke rust-test rust-lint tools-test clean re

all: check

# Rust tests + developer tooling tests (what Fusion's "network-core" runs).
check:
	CORE_CHECK_MODE=quick bash ci/core_check.sh

test: rust-test tools-test

# Loopback network with real binaries: raytracer (1 and 2 workers), sha256.
e2e:
	bash ci/e2e.sh

# Reverse proxy + TLS of infra/docker-compose.yml (needs Docker).
smoke:
	bash tests/smoke/run_proxy_smoke.sh

rust-test:
	cargo test --workspace --locked

rust-lint:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings

# Tests of tools/dev/ (UTF-8, locales, Solana preflight, Solana entrypoint).
tools-test:
	$(PYTHON) -m pytest -q

clean:
	cargo clean

re: clean all
