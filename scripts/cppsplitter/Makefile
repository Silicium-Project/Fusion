CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic
CC := gcc
CFLAGS := -O0 -g -no-pie

BINARIES := splitter fragment_executor
DEMO_BIN := demo/hello_demo
DEMO_OUT := demo/output
LOG_FILE := fragment_executor.log

PROGRAM ?=
RUN_NAME := $(basename $(notdir $(PROGRAM)))
RUN_BUILD_DIR := run_build
RUN_BIN := $(RUN_BUILD_DIR)/$(RUN_NAME)
RUN_OUT := $(if $(OUT),$(OUT),run_output/$(RUN_NAME))
RUN_LOG := $(if $(LOG),$(LOG),fragment_executor.log)
ARGS ?=

.PHONY: all clean demo demo-native demo-clean run run-native run-internal run-binary prep-program

all: $(BINARIES)

splitter: splitter.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

fragment_executor: fragment_executor.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

$(DEMO_BIN): demo/hello.c
	$(CC) $(CFLAGS) $< -o $@

demo: all $(DEMO_BIN)
	@rm -f $(LOG_FILE)
	@echo "==> Génération des partitions de démonstration"
	@rm -rf $(DEMO_OUT)
	./splitter $(DEMO_BIN) --output-dir $(DEMO_OUT)
	@echo "==> Exécution via fragment_executor (mode émulation)"
	./fragment_executor --summary $(DEMO_OUT)/summary.json --log $(LOG_FILE)

demo-native: all $(DEMO_BIN)
	@rm -f $(LOG_FILE)
	@echo "==> Génération des partitions de démonstration"
	@rm -rf $(DEMO_OUT)
	./splitter $(DEMO_BIN) --output-dir $(DEMO_OUT)
	@echo "==> Exécution via fragment_executor (mode natif - DANGEREUX, peut planter)"
	-./fragment_executor --summary $(DEMO_OUT)/summary.json --native --log $(LOG_FILE)

run: MODE = emulation
run: run-internal

run-native: MODE = native
run-native: run-internal

prep-program:
	@test -n "$(PROGRAM)" || { echo "Usage: make $@ PROGRAM=./source.c [OUT=dir] [LOG=logfile]"; exit 1; }
	@test -f "$(PROGRAM)" || { echo "Fichier source introuvable: $(PROGRAM)"; exit 1; }
	@mkdir -p $(RUN_BUILD_DIR)
	@rm -f $(RUN_BIN)
	@ext="$(suffix $(PROGRAM))"; \
	case "$$ext" in \
	  .c) echo "==> Compilation (C) de $(PROGRAM)"; $(CC) $(CFLAGS) $(PROGRAM) -o $(RUN_BIN) ;; \
	  .cpp|.cc|.cxx|.C|.c++) echo "==> Compilation (C++) de $(PROGRAM)"; $(CXX) $(CXXFLAGS) $(PROGRAM) -o $(RUN_BIN) ;; \
	  *) echo "Extension source non supportée: $$ext (attendu .c, .cc, .cxx, .cpp)"; exit 1 ;; \
	esac

run-internal: all prep-program
	@rm -f $(RUN_LOG)
	@echo "==> Partitionnement de $(RUN_BIN)"
	@rm -rf $(RUN_OUT)
	@mkdir -p $(dir $(RUN_OUT))
	./splitter $(RUN_BIN) --output-dir $(RUN_OUT)
	@echo "==> Exécution via fragment_executor ($(MODE))"
	@if [ "$(MODE)" = "native" ]; then \
		./fragment_executor --summary $(RUN_OUT)/summary.json --native --log $(RUN_LOG) || true; \
	else \
		./fragment_executor --summary $(RUN_OUT)/summary.json --log $(RUN_LOG); \
	fi

run-binary: all prep-program
	@echo "==> Exécution du binaire original: $(RUN_BIN) $(ARGS)"
	@$(RUN_BIN) $(ARGS)

demo-clean:
	@rm -rf $(DEMO_OUT) $(DEMO_BIN)

clean: demo-clean
	rm -f $(BINARIES) $(LOG_FILE)
