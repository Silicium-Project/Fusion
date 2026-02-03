REPO_ROOT := $(abspath ..)
CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic -fPIE
CPPFLAGS := -Iinclude -I../executor/include -MMD -MP
LDFLAGS :=
BUILDER_WRAPPER ?= $(REPO_ROOT)/worker/scripts/builder_wrapper.sh
FRAGMENT_GUI_BUILDER_IMAGE ?= luis1454/worker:builder

JANSSON_HEADER := $(firstword $(wildcard /usr/include/jansson.h /usr/local/include/jansson.h))
NEED_DOCKER_BUILD := $(if $(JANSSON_HEADER),,yes)

JOBS ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
MAKEFLAGS += -j$(JOBS)

LDLIBS := -ljansson -ldl
EXECUTOR_LIB_DIR := $(REPO_ROOT)/executor
LDFLAGS += -Wl,-rpath,'$$ORIGIN/../executor' -L$(EXECUTOR_LIB_DIR)
CPP_TEST_IMAGE ?= silicium/cpp-tests:latest
CPP_TEST_DOCKERFILE := $(REPO_ROOT)/infra/docker/cpp-tests/Dockerfile
CPP_TEST_CONTEXT := $(dir $(CPP_TEST_DOCKERFILE))
CCACHE_DIR := $(REPO_ROOT)/.cache/cpp-tests/ccache
CPP_TEST_CONTAINER ?= worker-test

SRC_DIR := src
OBJ_DIR := build
WORKER_OBJ_DIR := $(OBJ_DIR)/worker
BIN := worker
DYNAMO_RUNNER_BIN := dynamo_fragment_runner

SRC_FILES := $(shell find $(SRC_DIR) -type f -name '*.cpp')
RUNNER_MAIN_SRC := $(SRC_DIR)/dynamo_fragment_runner_main.cpp
WORKER_SRC := $(filter-out $(RUNNER_MAIN_SRC), $(SRC_FILES))
WORKER_OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(WORKER_OBJ_DIR)/%.o,$(WORKER_SRC))
WORKER_MAIN_OBJ := $(WORKER_OBJ_DIR)/main.o
WORKER_LIB_OBJS := $(filter-out $(WORKER_MAIN_OBJ), $(WORKER_OBJS))
DYNAMO_RUNNER_OBJ := $(WORKER_OBJ_DIR)/$(notdir $(RUNNER_MAIN_SRC:.cpp=.o))

TEST_SRCS := $(wildcard tests/*.cpp)
TEST_BUILD_DIR := $(OBJ_DIR)/tests
TEST_OBJ_DIR := $(TEST_BUILD_DIR)/obj
TEST_BIN := $(TEST_BUILD_DIR)/worker_tests
TEST_OBJS := $(patsubst tests/%.cpp,$(TEST_OBJ_DIR)/tests/%.o,$(TEST_SRCS))
TEST_WORKER_SRC := $(filter-out $(SRC_DIR)/main.cpp,$(WORKER_SRC))
TEST_WORKER_OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(TEST_OBJ_DIR)/worker/%.o,$(TEST_WORKER_SRC))
TEST_CXX ?= $(CXX)
TEST_CXXFLAGS ?= $(CXXFLAGS) --coverage
TEST_LDFLAGS ?= --coverage -lgtest -lgtest_main -pthread -L$(EXECUTOR_LIB_DIR) -Wl,-rpath,'$$ORIGIN/../../executor' -lfragment_emulator
CPP_TEST_LOCAL ?= 0

HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

.PHONY: all clean test test-clean build-cpp-test-image

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

$(TEST_BUILD_DIR):
	mkdir -p $(TEST_BUILD_DIR)

$(TEST_OBJ_DIR)/tests:
	mkdir -p $(TEST_OBJ_DIR)/tests

$(TEST_OBJ_DIR)/worker:
	mkdir -p $(TEST_OBJ_DIR)/worker

$(WORKER_OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(WORKER_OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BIN): $(WORKER_OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS) $(LDLIBS) -lfragment_emulator

$(DYNAMO_RUNNER_BIN): $(DYNAMO_RUNNER_OBJ) $(WORKER_LIB_OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS) $(LDLIBS) -lfragment_emulator

$(TEST_OBJ_DIR)/tests/%.o: tests/%.cpp | $(TEST_OBJ_DIR)/tests
	@mkdir -p $(dir $@)
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_OBJ_DIR)/worker/%.o: $(SRC_DIR)/%.cpp | $(TEST_OBJ_DIR)/worker
	@mkdir -p $(dir $@)
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_BIN): $(TEST_OBJS) $(TEST_WORKER_OBJS) | $(TEST_BUILD_DIR)
	$(TEST_CXX) $^ -o $@ $(TEST_LDFLAGS) $(LDLIBS)

clean:
	rm -f $(BIN) $(DYNAMO_RUNNER_BIN)
	rm -rf $(OBJ_DIR)

test-clean:
	@# Nettoyage des traces gcov pour éviter les warnings lors des tests.
	@test ! -d $(OBJ_DIR) || find $(OBJ_DIR) -type f \( -name '*.gcda' -o -name '*.gcno' \) -delete

ifeq ($(CPP_TEST_LOCAL),1)
test:
	$(MAKE) test-clean
	$(MAKE) -C $(EXECUTOR_LIB_DIR)
	$(MAKE) $(TEST_BIN)
	LD_LIBRARY_PATH=$(EXECUTOR_LIB_DIR) $(TEST_BIN)
else
test: build-cpp-test-image
	@mkdir -p $(CCACHE_DIR)
	@if ! docker ps --format '{{.Names}}' | grep -qx $(CPP_TEST_CONTAINER); then \
		echo ">> Starting test container $(CPP_TEST_CONTAINER)"; \
		docker run -d --name $(CPP_TEST_CONTAINER) \
			-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
			-e CCACHE_DIR=/ccache \
			-v $(abspath ..):/workspace:Z -w /workspace \
			-v $(CCACHE_DIR):/ccache \
			$(CPP_TEST_IMAGE) tail -f /dev/null >/dev/null; \
	fi
	docker exec $(CPP_TEST_CONTAINER) bash -lc '\
		set -euo pipefail; \
		ccache -M 2G >/dev/null; \
		cd /workspace && make -C executor; \
		cd worker; \
		make test-clean; \
		env TEST_CXX="ccache g++" make $(TEST_BIN); \
		LD_LIBRARY_PATH=/workspace/executor $(TEST_BIN); \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID worker/build'
endif

build-cpp-test-image:
	@docker image inspect $(CPP_TEST_IMAGE) >/dev/null 2>&1 || \
		(echo ">> Building $(CPP_TEST_IMAGE) image (one-time setup)"; \
		 docker build -t $(CPP_TEST_IMAGE) -f $(CPP_TEST_DOCKERFILE) $(CPP_TEST_CONTEXT))

-include $(WORKER_OBJS:.o=.d) \
         $(DYNAMO_RUNNER_OBJ:.o=.d) \
         $(TEST_OBJS:.o=.d) \
         $(TEST_WORKER_OBJS:.o=.d)
