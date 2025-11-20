REPO_ROOT := $(abspath ../..)
CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic -fPIE
CPPFLAGS := -Iinclude -I../fragment/executor/include -MMD -MP
BUILDER_WRAPPER ?= $(REPO_ROOT)/tools/worker/scripts/builder_wrapper.sh
FRAGMENT_GUI_BUILDER_IMAGE ?= luis1454/worker:1.0

JANSSON_HEADER := $(firstword $(wildcard /usr/include/jansson.h /usr/local/include/jansson.h))
NEED_DOCKER_BUILD := $(if $(JANSSON_HEADER),,yes)

JOBS ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
MAKEFLAGS += -j$(JOBS)

LDLIBS := -ljansson
CPP_TEST_IMAGE ?= silicium/cpp-tests:latest
CPP_TEST_DOCKERFILE := $(REPO_ROOT)/infra/docker/cpp-tests/Dockerfile
CPP_TEST_CONTEXT := $(dir $(CPP_TEST_DOCKERFILE))
CCACHE_DIR := $(REPO_ROOT)/.cache/cpp-tests/ccache

SRC_DIR := src
OBJ_DIR := build
WORKER_OBJ_DIR := $(OBJ_DIR)/worker
FRAGMENT_OBJ_DIR := $(OBJ_DIR)/fragment
BIN := worker
DYNAMO_RUNNER_BIN := dynamo_fragment_runner

ALL_SRCS := $(wildcard $(SRC_DIR)/*.cpp)
RUNNER_MAIN_SRC := $(SRC_DIR)/dynamo_fragment_runner_main.cpp
WORKER_SRC := $(filter-out $(RUNNER_MAIN_SRC), $(ALL_SRCS))
WORKER_OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(WORKER_OBJ_DIR)/%.o,$(WORKER_SRC))
WORKER_MAIN_OBJ := $(WORKER_OBJ_DIR)/main.o
WORKER_LIB_OBJS := $(filter-out $(WORKER_MAIN_OBJ), $(WORKER_OBJS))
DYNAMO_RUNNER_OBJ := $(WORKER_OBJ_DIR)/$(notdir $(RUNNER_MAIN_SRC:.cpp=.o))

FRAGMENT_SRC_DIR := ../fragment/executor/src
FRAGMENT_SOURCES := fragment_executor.cpp register_emulator.cpp instruction_emulator.cpp \
	segment_loader.cpp execution_result.cpp logging.cpp utils.cpp cli.cpp partition_summary.cpp
FRAGMENT_OBJS := $(patsubst %.cpp,$(FRAGMENT_OBJ_DIR)/%.o,$(FRAGMENT_SOURCES))

TEST_SRCS := tests/queue_loader_test.cpp tests/worker_runner_test.cpp tests/stateful_worker_test.cpp
TEST_BUILD_DIR := $(OBJ_DIR)/tests
TEST_OBJ_DIR := $(TEST_BUILD_DIR)/obj
TEST_BIN := $(TEST_BUILD_DIR)/worker_tests
TEST_OBJS := $(patsubst tests/%.cpp,$(TEST_OBJ_DIR)/tests/%.o,$(TEST_SRCS))
TEST_WORKER_OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(TEST_OBJ_DIR)/worker/%.o,$(filter-out $(SRC_DIR)/main.cpp,$(WORKER_SRC)))
TEST_FRAGMENT_OBJS := $(patsubst %.cpp,$(TEST_OBJ_DIR)/fragment/%.o,$(FRAGMENT_SOURCES))
TEST_CXX ?= $(CXX)
TEST_CXXFLAGS ?= $(CXXFLAGS) --coverage
TEST_LDFLAGS ?= --coverage -lgtest -lgtest_main -pthread

HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

.PHONY: all clean test build-cpp-test-image

ifeq ($(NEED_DOCKER_BUILD),yes)
ifndef IN_DOCKER_BUILD
all:
	@echo "[worker] libjansson-devel introuvable, compilation via conteneur..."
	@$(BUILDER_WRAPPER) env IN_DOCKER_BUILD=1 $(MAKE) -C $(CURDIR)
	@exit 0
else
all: $(BIN) $(DYNAMO_RUNNER_BIN)
endif
else
all: $(BIN) $(DYNAMO_RUNNER_BIN)
endif

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(WORKER_OBJ_DIR):
	mkdir -p $(WORKER_OBJ_DIR)

$(FRAGMENT_OBJ_DIR):
	mkdir -p $(FRAGMENT_OBJ_DIR)

$(TEST_BUILD_DIR):
	mkdir -p $(TEST_BUILD_DIR)

$(TEST_OBJ_DIR)/tests:
	mkdir -p $(TEST_OBJ_DIR)/tests

$(TEST_OBJ_DIR)/worker:
	mkdir -p $(TEST_OBJ_DIR)/worker

$(TEST_OBJ_DIR)/fragment:
	mkdir -p $(TEST_OBJ_DIR)/fragment

$(WORKER_OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(WORKER_OBJ_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(FRAGMENT_OBJ_DIR)/%.o: $(FRAGMENT_SRC_DIR)/%.cpp | $(FRAGMENT_OBJ_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BIN): $(WORKER_OBJS) $(FRAGMENT_OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDLIBS)

$(DYNAMO_RUNNER_BIN): $(DYNAMO_RUNNER_OBJ) $(WORKER_LIB_OBJS) $(FRAGMENT_OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDLIBS)

$(TEST_OBJ_DIR)/tests/%.o: tests/%.cpp | $(TEST_OBJ_DIR)/tests
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_OBJ_DIR)/worker/%.o: $(SRC_DIR)/%.cpp | $(TEST_OBJ_DIR)/worker
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_OBJ_DIR)/fragment/%.o: $(FRAGMENT_SRC_DIR)/%.cpp | $(TEST_OBJ_DIR)/fragment
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_BIN): $(TEST_OBJS) $(TEST_WORKER_OBJS) $(TEST_FRAGMENT_OBJS) | $(TEST_BUILD_DIR)
	$(TEST_CXX) $^ -o $@ $(TEST_LDFLAGS) $(LDLIBS)

clean:
	rm -f $(BIN) $(DYNAMO_RUNNER_BIN)
	rm -rf $(OBJ_DIR)

test: build-cpp-test-image
	@mkdir -p $(CCACHE_DIR)
	docker run --rm \
		-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
		-e CCACHE_DIR=/ccache \
		-v $(abspath ../..):/workspace:Z -w /workspace \
		-v $(CCACHE_DIR):/ccache \
		$(CPP_TEST_IMAGE) bash -lc '\
		set -euo pipefail; \
		ccache -M 2G >/dev/null; \
		cd tools/worker; \
		env TEST_CXX="ccache g++" make $(TEST_BIN); \
		$(TEST_BIN); \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID tools/worker/build'

build-cpp-test-image:
	@docker image inspect $(CPP_TEST_IMAGE) >/dev/null 2>&1 || \
		(echo ">> Building $(CPP_TEST_IMAGE) image (one-time setup)"; \
		 docker build -t $(CPP_TEST_IMAGE) -f $(CPP_TEST_DOCKERFILE) $(CPP_TEST_CONTEXT))

-include $(WORKER_OBJS:.o=.d) \
         $(FRAGMENT_OBJS:.o=.d) \
         $(DYNAMO_RUNNER_OBJ:.o=.d) \
         $(TEST_OBJS:.o=.d) \
         $(TEST_WORKER_OBJS:.o=.d) \
         $(TEST_FRAGMENT_OBJS:.o=.d)
