CXX := g++
CXXFLAGS := -std=c++17 -O2 -g -Wall -Wextra -pedantic -fPIE
CC := gcc
CFLAGS := -O0 -g -no-pie

JOBS ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
MAKEFLAGS += -j$(JOBS)

SRC_DIR := src
REPO_ROOT := $(abspath ../../..)
CPP_TEST_IMAGE ?= silicium/cpp-tests:latest
CPP_TEST_DOCKERFILE := $(REPO_ROOT)/infra/docker/cpp-tests/Dockerfile
CPP_TEST_CONTEXT := $(dir $(CPP_TEST_DOCKERFILE))
CCACHE_DIR := $(REPO_ROOT)/.cache/cpp-tests/ccache
SPLITTER_BIN := splitter
EXECUTOR_DIR := ../executor
EXECUTOR_BIN := $(EXECUTOR_DIR)/fragment_executor
DEMO_SRC := $(REPO_ROOT)/tools/demo/fragment/hello.c
DEMO_BIN := run_build/hello_demo
DEMO_OUT := run_output/demo
LOG_FILE := fragment_executor.log

PROGRAM ?=
define resolve_prog
$(if $(wildcard $(abspath $(1))),$(abspath $(1)),$(if $(wildcard $(REPO_ROOT)/$(1)),$(REPO_ROOT)/$(1),))
endef

PROGRAM_RESOLVED := $(call resolve_prog,$(PROGRAM))
RUN_NAME := $(basename $(notdir $(if $(PROGRAM_RESOLVED),$(PROGRAM_RESOLVED),$(PROGRAM))))
RUN_BUILD_DIR := run_build
RUN_BIN := $(RUN_BUILD_DIR)/$(RUN_NAME)
RUN_OUT := $(if $(OUT),$(OUT),run_output/$(RUN_NAME))
RUN_LOG := $(if $(LOG),$(LOG),fragment_executor.log)
ARGS ?=
PROGRAM_LIBS ?= -lavformat -lavcodec -lavutil -lswscale -lm -lcsfml-graphics -lcsfml-window -lcsfml-system
BUILDER_WRAPPER ?= $(REPO_ROOT)/tools/worker/scripts/builder_wrapper.sh
BUILD_WITH_DOCKER ?= $(BUILDER_WRAPPER)

.PHONY: all clean fclean re demo demo-native demo-native-force demo-clean run run-native run-internal run-binary prep-program executor test build-cpp-test-image

SRC_FILES := $(shell find $(SRC_DIR) -name '*.cpp')
OBJ_DIR := build
OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(OBJ_DIR)/%.o,$(SRC_FILES))
CPPFLAGS := -Iinclude

TEST_SRCS := tests/pipeline_config_test.cpp tests/instruction_analysis_test.cpp tests/disassembly_test.cpp tests/hash_test.cpp tests/partitioner_test.cpp tests/summary_writer_test.cpp tests/flat_map_test.cpp tests/pipeline_integration_test.cpp
TEST_EXTRA_SRCS := $(filter-out $(SRC_DIR)/main.cpp,$(SRC_FILES))
TEST_BUILD_DIR := build/tests
TEST_OBJ_DIR := $(TEST_BUILD_DIR)/obj
TEST_BIN := $(TEST_BUILD_DIR)/splitter_tests
TEST_TEST_OBJS := $(patsubst tests/%.cpp,$(TEST_OBJ_DIR)/tests/%.o,$(TEST_SRCS))
TEST_EXTRA_OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(TEST_OBJ_DIR)/src/%.o,$(TEST_EXTRA_SRCS))
TEST_OBJS := $(TEST_TEST_OBJS) $(TEST_EXTRA_OBJS)
TEST_CXX ?= $(CXX)
TEST_CXXFLAGS ?= $(CXXFLAGS) --coverage
TEST_LDFLAGS ?= --coverage -lgtest -lgtest_main -pthread

all: $(SPLITTER_BIN)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(SPLITTER_BIN): $(OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@

$(TEST_BUILD_DIR):
	mkdir -p $(TEST_BUILD_DIR)

$(TEST_OBJ_DIR)/tests:
	mkdir -p $(TEST_OBJ_DIR)/tests

$(TEST_OBJ_DIR)/src:
	mkdir -p $(TEST_OBJ_DIR)/src

$(TEST_OBJ_DIR)/tests/%.o: tests/%.cpp | $(TEST_OBJ_DIR)/tests
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_OBJ_DIR)/src/%.o: $(SRC_DIR)/%.cpp | $(TEST_OBJ_DIR)/src
	@mkdir -p $(dir $@)
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_BIN): $(TEST_OBJS) | $(TEST_BUILD_DIR)
	$(TEST_CXX) $(TEST_OBJS) -o $@ $(TEST_LDFLAGS)

executor: $(EXECUTOR_BIN)

$(EXECUTOR_BIN):
	$(MAKE) -C $(EXECUTOR_DIR)

$(DEMO_BIN): $(DEMO_SRC)
	@mkdir -p $(dir $(DEMO_BIN))
	$(CC) $(CFLAGS) $(DEMO_SRC) -o $@

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

demo-native-force: all executor $(DEMO_BIN)
	@rm -f $(LOG_FILE)
	@echo "==> Génération des partitions de démonstration"
	@rm -rf $(DEMO_OUT)
	./splitter $(DEMO_BIN) --output-dir $(DEMO_OUT)
	@echo "==> Exécution via fragment_executor (mode natif FORCÉ - très dangereux)"
	-$(EXECUTOR_BIN) --summary $(DEMO_OUT)/summary.json --native --native-force --log $(LOG_FILE)

run: MODE = emulation
run: run-internal

run-native: MODE = native
run-native: run-internal

prep-program:
	@test -n "$(PROGRAM)" || { echo "Usage: make $@ PROGRAM=./source.c [OUT=dir] [LOG=logfile]"; exit 1; }
	@prog="$(PROGRAM_RESOLVED)"; \
	if [ -z "$$prog" ] || [ ! -f "$$prog" ]; then \
		echo "Fichier source introuvable: $(PROGRAM)"; exit 1; \
	fi; \
	mkdir -p $(RUN_BUILD_DIR); \
	rm -f $(RUN_BIN); \
	ext="$${prog##*.}"; \
	case "$$ext" in \
  c) echo "==> Compilation (C) de $$prog"; $(BUILD_WITH_DOCKER) gcc -O0 -g -no-pie "$$prog" -o $(RUN_BIN) $(PROGRAM_LIBS) ;; \
  cpp|cc|cxx|C|c++) echo "==> Compilation (C++) de $$prog"; $(BUILD_WITH_DOCKER) g++ $(CXXFLAGS) "$$prog" -o $(RUN_BIN) $(PROGRAM_LIBS) ;; \
  *) echo "Extension source non supportée: $$ext (attendu c, cc, cxx, cpp)"; exit 1 ;; \
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

test: build-cpp-test-image
	@mkdir -p $(CCACHE_DIR)
	docker run --rm \
		-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
		-e CCACHE_DIR=/ccache \
		-v $(abspath ../../..):/workspace:Z -w /workspace \
		-v $(CCACHE_DIR):/ccache \
		$(CPP_TEST_IMAGE) bash -lc '\
		set -euo pipefail; \
		ccache -M 2G >/dev/null; \
		cd tools/fragment/splitter; \
		env TEST_CXX="ccache g++" $(MAKE) $(TEST_BIN); \
		$(TEST_BIN); \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID tools/fragment/splitter/build && rm -f tools/fragment/splitter/*.gcov'

build-cpp-test-image:
	@docker image inspect $(CPP_TEST_IMAGE) >/dev/null 2>&1 || \
		(echo ">> Building $(CPP_TEST_IMAGE) image (one-time setup)"; \
		 docker build -t $(CPP_TEST_IMAGE) -f $(CPP_TEST_DOCKERFILE) $(CPP_TEST_CONTEXT))

demo-clean:
	@rm -rf $(DEMO_OUT) $(DEMO_BIN)

clean: demo-clean
	rm -f $(SPLITTER_BIN) $(LOG_FILE)
	rm -rf $(OBJ_DIR)

fclean: clean
	rm -rf $(RUN_BUILD_DIR) run_output

re: fclean all
