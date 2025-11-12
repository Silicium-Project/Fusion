CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic
CC := gcc
CFLAGS := -O0 -g -no-pie

SRC_DIR := src
SPLITTER_BIN := splitter
EXECUTOR_DIR := ../fragment-executor
EXECUTOR_BIN := $(EXECUTOR_DIR)/fragment_executor
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

.PHONY: all clean fclean re demo demo-native demo-clean run run-native run-internal run-binary prep-program executor test

SRC_FILES := $(wildcard $(SRC_DIR)/*.cpp)
OBJ_DIR := build
OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(OBJ_DIR)/%.o,$(SRC_FILES))
CPPFLAGS := -Iinclude

TEST_SRCS := tests/pipeline_config_test.cpp tests/instruction_analysis_test.cpp tests/disassembly_test.cpp
TEST_EXTRA_SRCS := src/instruction_analysis.cpp src/disassembly.cpp src/util.cpp
TEST_BUILD_DIR := build/tests

all: $(SPLITTER_BIN)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(SPLITTER_BIN): $(OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@

executor: $(EXECUTOR_BIN)

$(EXECUTOR_BIN):
	$(MAKE) -C $(EXECUTOR_DIR)

$(DEMO_BIN): demo/hello.c
	$(CC) $(CFLAGS) $< -o $@

demo: all executor $(DEMO_BIN)
	@rm -f $(LOG_FILE)
	@echo "==> Génération des partitions de démonstration"
	@rm -rf $(DEMO_OUT)
	./splitter $(DEMO_BIN) --output-dir $(DEMO_OUT)
	@echo "==> Exécution via fragment_executor (mode émulation)"
	$(EXECUTOR_BIN) --summary $(DEMO_OUT)/summary.json --log $(LOG_FILE)

demo-native: all executor $(DEMO_BIN)
	@rm -f $(LOG_FILE)
	@echo "==> Génération des partitions de démonstration"
	@rm -rf $(DEMO_OUT)
	./splitter $(DEMO_BIN) --output-dir $(DEMO_OUT)
	@echo "==> Exécution via fragment_executor (mode natif - DANGEREUX, peut planter)"
	-$(EXECUTOR_BIN) --summary $(DEMO_OUT)/summary.json --native --log $(LOG_FILE)

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

run-internal: all executor prep-program
	@rm -f $(RUN_LOG)
	@echo "==> Partitionnement de $(RUN_BIN)"
	@rm -rf $(RUN_OUT)
	@mkdir -p $(dir $(RUN_OUT))
	./splitter $(RUN_BIN) --output-dir $(RUN_OUT)
	@echo "==> Exécution via fragment_executor ($(MODE))"
	@if [ "$(MODE)" = "native" ]; then \
		$(EXECUTOR_BIN) --summary $(RUN_OUT)/summary.json --native --log $(RUN_LOG) || true; \
	else \
		$(EXECUTOR_BIN) --summary $(RUN_OUT)/summary.json --log $(RUN_LOG); \
	fi

run-binary: all prep-program
	@echo "==> Exécution du binaire original: $(RUN_BIN) $(ARGS)"
	@$(RUN_BIN) $(ARGS)

HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

test:
	docker run --rm \
		-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
		-v $(abspath ../../..):/workspace:Z -w /workspace \
		debian:bookworm-slim bash -lc '\
		set -euo pipefail; \
		apt-get update >/dev/null && apt-get install -y --no-install-recommends build-essential cmake libgtest-dev lcov >/dev/null; \
		cmake -S /usr/src/googletest -B /tmp/gtest >/dev/null && cmake --build /tmp/gtest >/dev/null && cmake --install /tmp/gtest >/dev/null; \
	cd tools/experiments/splitter; \
	rm -rf $(TEST_BUILD_DIR) && mkdir -p $(TEST_BUILD_DIR); \
	g++ -Iinclude -std=c++17 -O2 -Wall -Wextra -pedantic --coverage \
		$(TEST_SRCS) $(TEST_EXTRA_SRCS) \
		-o $(TEST_BUILD_DIR)/splitter_tests --coverage -lgtest -lgtest_main -pthread; \
	$(TEST_BUILD_DIR)/splitter_tests; \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID tools/experiments/splitter/build && rm -f tools/experiments/splitter/*.gcov'

demo-clean:
	@rm -rf $(DEMO_OUT) $(DEMO_BIN)

clean: demo-clean
	rm -f $(SPLITTER_BIN) $(LOG_FILE)
	rm -rf $(OBJ_DIR)

fclean: clean
	rm -rf $(RUN_BUILD_DIR) run_output

re: fclean all
