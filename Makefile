SHELL := /bin/bash
CLI := ./silicium

.PHONY: test smoke tools-demo clean clean-tools clean-ledgers fclean

test:
	$(CLI) test

smoke:
	$(CLI) smoke

tools-demo:
	$(CLI) tools demo

clean:
	$(CLI) clean

clean-tools:
	$(CLI) tools clean

clean-ledgers:
	$(CLI) ledger wipe --all

fclean:
	$(CLI) clean --ledgers
