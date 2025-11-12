SHELL := /bin/bash

.PHONY: all splitter executor worker demo demo-native run run-native run-binary test clean fclean re

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

run: splitter executor
	$(MAKE) -C tools/experiments/splitter run

run-native: splitter executor
	$(MAKE) -C tools/experiments/splitter run-native

run-binary: splitter
	$(MAKE) -C tools/experiments/splitter run-binary

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
