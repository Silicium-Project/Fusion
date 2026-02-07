REPO_ROOT := $(abspath ..)
CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic -fPIC
LDFLAGS := -pie
CPPFLAGS := -Iinclude
BUILDER_WRAPPER ?= $(REPO_ROOT)/worker/scripts/builder_wrapper.sh
FRAGMENT_GUI_BUILDER_IMAGE ?= luis1454/worker:builder

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
BIN := fragment_executor
BIN_EMU := fragment_emulator
LIB_NATIVE := libfragment_executor.so
LIB_EMU := libfragment_emulator.so

# Sources partagées
COMMON_SRC := cli/ArgParser.cpp cli/Cli.cpp core/ExecutionResult.cpp core/FragmentExecutor.cpp \
	support/Hash.cpp core/InstructionEmulator.cpp core/PrintfEmulator.cpp support/JsonHasher.cpp support/Logging.cpp \
	cli/OptionParser.cpp partition/PartitionRegistry.cpp partition/PartitionSummary.cpp \
	core/RegisterEmulator.cpp runtime/Runner.cpp core/SegmentLoader.cpp support/Utils.cpp \
	core/Opcodes.cpp

EMU_LIB_SRC := $(COMMON_SRC) backend/ExecutionBackendEmu.cpp backend/EmulatedExecutionBackend.cpp \
	runtime/EmulatedRunner.cpp api/FragmentApi.cpp
NATIVE_LIB_SRC := $(COMMON_SRC) backend/ExecutionBackendNative.cpp backend/NativeExecutionBackend.cpp \
	runtime/NativeRunner.cpp api/FragmentApi.cpp

EMU_BIN_SRC := $(EMU_LIB_SRC) Main.cpp
NATIVE_BIN_SRC := $(NATIVE_LIB_SRC) Main.cpp

OBJS_EMU_BIN := $(addprefix $(OBJ_DIR)/emu_bin/,$(EMU_BIN_SRC:.cpp=.o))
OBJS_NATIVE_BIN := $(addprefix $(OBJ_DIR)/native_bin/,$(NATIVE_BIN_SRC:.cpp=.o))
OBJS_EMU_LIB := $(addprefix $(OBJ_DIR)/emu_lib/,$(EMU_LIB_SRC:.cpp=.o))
OBJS_NATIVE_LIB := $(addprefix $(OBJ_DIR)/native_lib/,$(NATIVE_LIB_SRC:.cpp=.o))

TEST_SRCS := tests/config_test.cpp tests/opcode_test.cpp tests/executor_test.cpp tests/instruction_emulator_test.cpp \
	tests/printf_emulation_test.cpp tests/support_test.cpp tests/native_runner_test.cpp
TEST_EXTRA_SRCS := src/core/FragmentExecutor.cpp src/core/RegisterEmulator.cpp src/core/PrintfEmulator.cpp src/support/Utils.cpp src/support/Logging.cpp \
	src/core/ExecutionResult.cpp src/core/InstructionEmulator.cpp src/core/SegmentLoader.cpp src/core/Opcodes.cpp src/runtime/NativeRunner.cpp src/partition/PartitionRegistry.cpp
TEST_BUILD_DIR := $(OBJ_DIR)/tests
TEST_OBJ_DIR := $(TEST_BUILD_DIR)/obj
TEST_BIN := $(TEST_BUILD_DIR)/fragment_tests
TEST_TEST_OBJS := $(patsubst tests/%.cpp,$(TEST_OBJ_DIR)/tests/%.o,$(TEST_SRCS))
TEST_EXTRA_OBJS := $(patsubst src/%.cpp,$(TEST_OBJ_DIR)/src/%.o,$(TEST_EXTRA_SRCS))
TEST_OBJS := $(TEST_TEST_OBJS) $(TEST_EXTRA_OBJS)
TEST_CXX ?= $(CXX)
TEST_CXXFLAGS ?= $(CXXFLAGS) --coverage
TEST_LDFLAGS ?= --coverage -lgtest -lgtest_main -pthread
CPP_TEST_LOCAL ?= 0
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

.PHONY: all clean test test-clean build-cpp-test-image

ifeq ($(NEED_DOCKER_BUILD),yes)
ifndef IN_DOCKER_BUILD
all:
	@echo "[fragment-executor] libjansson-devel introuvable, compilation via conteneur..."
	@$(BUILDER_WRAPPER) env IN_DOCKER_BUILD=1 $(MAKE) -C $(CURDIR)
	@exit 0
else
all: $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU)
endif
else
all: $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU)
endif

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/emu_bin/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJ_DIR)/native_bin/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJ_DIR)/emu_lib/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJ_DIR)/native_lib/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BIN): $(OBJS_NATIVE_BIN)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS) $(LDLIBS)

$(BIN_EMU): $(OBJS_EMU_BIN)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS) $(LDLIBS)

$(LIB_NATIVE): $(OBJS_NATIVE_LIB)
	$(CXX) $(CXXFLAGS) -shared $^ -o $@ $(LDLIBS)

$(LIB_EMU): $(OBJS_EMU_LIB)
	$(CXX) $(CXXFLAGS) -shared $^ -o $@ $(LDLIBS)
$(TEST_BUILD_DIR):
	mkdir -p $(TEST_BUILD_DIR)

$(TEST_OBJ_DIR)/tests:
	mkdir -p $(TEST_OBJ_DIR)/tests

$(TEST_OBJ_DIR)/src:
	mkdir -p $(TEST_OBJ_DIR)/src

$(TEST_OBJ_DIR)/tests/%.o: tests/%.cpp | $(TEST_OBJ_DIR)/tests
	@mkdir -p $(dir $@)
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_OBJ_DIR)/src/%.o: src/%.cpp | $(TEST_OBJ_DIR)/src
	@mkdir -p $(dir $@)
	$(TEST_CXX) $(CPPFLAGS) $(TEST_CXXFLAGS) -c $< -o $@

$(TEST_BIN): $(TEST_OBJS) | $(TEST_BUILD_DIR)
	$(TEST_CXX) $(TEST_OBJS) -o $@ $(TEST_LDFLAGS) $(LDLIBS)

clean:
	rm -f $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU)
	@if [ -d $(OBJ_DIR) ]; then \
		chmod -R u+rwX $(OBJ_DIR) >/dev/null 2>&1 || true; \
		rm -rf $(OBJ_DIR) 2>/dev/null || { \
			if command -v sudo >/dev/null 2>&1 && sudo -n rm -rf $(OBJ_DIR) 2>/dev/null; then :; \
			elif command -v docker >/dev/null 2>&1 && docker run --rm -v $(abspath .):/workspace busybox sh -c 'rm -rf /workspace/$(OBJ_DIR)'; then :; \
			else \
				echo "Échec du nettoyage $(OBJ_DIR) (droits manquants)"; exit 1; \
			fi; }; \
	fi

test-clean:
	@# Nettoyage des traces gcov pour éviter les warnings lors des tests.
	@test ! -d $(OBJ_DIR) || find $(OBJ_DIR) -type f \( -name '*.gcda' -o -name '*.gcno' \) -delete

ifeq ($(CPP_TEST_LOCAL),1)
test:
	$(MAKE) test-clean
	$(MAKE) $(TEST_BIN)
	$(TEST_BIN)
else
test: build-cpp-test-image
	@mkdir -p $(CCACHE_DIR)
	docker run --rm \
		-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
		-e CCACHE_DIR=/ccache \
		-v $(abspath ..):/workspace:Z -w /workspace \
		-v $(CCACHE_DIR):/ccache \
		$(CPP_TEST_IMAGE) bash -lc '\
		set -euo pipefail; \
		ccache -M 2G >/dev/null; \
		cd executor; \
		$(MAKE) test-clean; \
		env TEST_CXX="ccache g++" $(MAKE) $(TEST_BIN); \
		$(TEST_BIN); \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID executor/$(OBJ_DIR)'
endif

build-cpp-test-image:
	@docker image inspect $(CPP_TEST_IMAGE) >/dev/null 2>&1 || \
		(echo ">> Building $(CPP_TEST_IMAGE) image (one-time setup)"; \
		 docker build -t $(CPP_TEST_IMAGE) -f $(CPP_TEST_DOCKERFILE) $(CPP_TEST_CONTEXT))
