REPO_ROOT := $(abspath ..)
CXX := g++
AR ?= ar
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic -fPIC
LDFLAGS := -pie
CPPFLAGS := -Iinclude -MMD -MP
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
CPP_TEST_USE_CCACHE ?= 0
CPP_TEST_USE_CCACHE_BOOL := $(if $(filter 1 true yes on,$(CPP_TEST_USE_CCACHE)),1,0)
CPP_TEST_JOBS ?= 2
ifeq ($(CPP_TEST_USE_CCACHE_BOOL),1)
CPP_TEST_COMPILER := ccache g++
CPP_TEST_CCACHE_WARMUP := ccache -M 2G >/dev/null;
else
CPP_TEST_COMPILER := g++
CPP_TEST_CCACHE_WARMUP := true;
endif

SRC_DIR := src
OBJ_DIR := build
BIN := fragment_executor
BIN_EMU := fragment_emulator
LIB_NATIVE := libfragment_executor.so
LIB_EMU := libfragment_emulator.so
LIB_NATIVE_STATIC := libfragment_executor.a
LIB_EMU_STATIC := libfragment_emulator.a

# Sources partagées
COMMON_SRC := cli/ArgParser.cpp cli/Cli.cpp core/ExecutionResult.cpp core/FragmentExecutor.cpp \
	support/Hash.cpp core/InstructionEmulator.cpp core/PrintfEmulator.cpp support/JsonHasher.cpp support/Logging.cpp \
	support/StructuredRunLogger.cpp \
	cli/OptionParser.cpp partition/PartitionRegistry.cpp partition/PartitionSummary.cpp \
	core/RegisterEmulator.cpp runtime/Runner.cpp core/SegmentLoader.cpp support/Utils.cpp \
	core/Opcodes.cpp api/FragmentApiResultAdapter.cpp

EMU_CORE_SRC := $(COMMON_SRC) backend/ExecutionBackendEmu.cpp backend/EmulatedExecutionBackend.cpp \
	runtime/EmulatedRunner.cpp api/FragmentApi.cpp
NATIVE_CORE_SRC := $(COMMON_SRC) backend/ExecutionBackendNative.cpp backend/NativeExecutionBackend.cpp \
	runtime/NativeRunner.cpp api/FragmentApi.cpp
MAIN_SRC := Main.cpp

OBJS_EMU_CORE := $(addprefix $(OBJ_DIR)/emu/,$(EMU_CORE_SRC:.cpp=.o))
OBJS_NATIVE_CORE := $(addprefix $(OBJ_DIR)/native/,$(NATIVE_CORE_SRC:.cpp=.o))
OBJ_MAIN := $(OBJ_DIR)/common/$(MAIN_SRC:.cpp=.o)

TEST_SRCS := tests/config_test.cpp tests/opcode_test.cpp tests/executor_test.cpp tests/instruction_emulator_test.cpp \
	tests/printf_emulation_test.cpp tests/support_test.cpp tests/native_runner_test.cpp tests/interface_contract_compat_test.cpp \
	tests/fragment_api_result_adapter_test.cpp
TEST_EXTRA_SRCS := src/core/FragmentExecutor.cpp src/core/RegisterEmulator.cpp src/core/PrintfEmulator.cpp src/support/Utils.cpp src/support/Logging.cpp src/support/StructuredRunLogger.cpp \
	src/core/ExecutionResult.cpp src/core/InstructionEmulator.cpp src/core/SegmentLoader.cpp src/core/Opcodes.cpp src/runtime/NativeRunner.cpp src/partition/PartitionRegistry.cpp \
	src/api/FragmentApiResultAdapter.cpp
TEST_BUILD_DIR := $(OBJ_DIR)/tests
TEST_OBJ_DIR := $(TEST_BUILD_DIR)/obj
TEST_BIN := $(TEST_BUILD_DIR)/fragment_tests
TEST_SUPPORT_LIB := $(TEST_BUILD_DIR)/libexecutor_test_support.a
TEST_TEST_OBJS := $(patsubst tests/%.cpp,$(TEST_OBJ_DIR)/tests/%.o,$(TEST_SRCS))
TEST_EXTRA_OBJS := $(patsubst src/%.cpp,$(TEST_OBJ_DIR)/src/%.o,$(TEST_EXTRA_SRCS))
TEST_OBJS := $(TEST_TEST_OBJS) $(TEST_EXTRA_OBJS)
TEST_CXX ?= $(CXX)
TEST_CXXFLAGS ?= $(CXXFLAGS) --coverage
TEST_LDFLAGS ?= --coverage -lgtest -lgtest_main -pthread
CPP_TEST_LOCAL ?= 0
CPP_TEST_FORCE_REBUILD ?= 0
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

.PHONY: all clean test test-clean test-reset-counters build-cpp-test-image

ifeq ($(NEED_DOCKER_BUILD),yes)
ifndef IN_DOCKER_BUILD
all:
	@echo "[fragment-executor] libjansson-devel introuvable, compilation via conteneur..."
	@$(BUILDER_WRAPPER) env IN_DOCKER_BUILD=1 $(MAKE) -C $(CURDIR)
	@exit 0
else
all: $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU) $(LIB_NATIVE_STATIC) $(LIB_EMU_STATIC)
endif
else
all: $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU) $(LIB_NATIVE_STATIC) $(LIB_EMU_STATIC)
endif

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/emu/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJ_DIR)/native/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJ_MAIN): $(SRC_DIR)/$(MAIN_SRC) | $(OBJ_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(LIB_NATIVE_STATIC): $(OBJS_NATIVE_CORE)
	$(AR) rcs $@ $^

$(LIB_EMU_STATIC): $(OBJS_EMU_CORE)
	$(AR) rcs $@ $^

$(BIN): $(OBJ_MAIN) $(LIB_NATIVE_STATIC)
	$(CXX) $(CXXFLAGS) $(OBJ_MAIN) $(LIB_NATIVE_STATIC) -o $@ $(LDFLAGS) $(LDLIBS)

$(BIN_EMU): $(OBJ_MAIN) $(LIB_EMU_STATIC)
	$(CXX) $(CXXFLAGS) $(OBJ_MAIN) $(LIB_EMU_STATIC) -o $@ $(LDFLAGS) $(LDLIBS)

$(LIB_NATIVE): $(OBJS_NATIVE_CORE)
	$(CXX) $(CXXFLAGS) -shared $^ -o $@ $(LDLIBS)

$(LIB_EMU): $(OBJS_EMU_CORE)
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

$(TEST_SUPPORT_LIB): $(TEST_EXTRA_OBJS) | $(TEST_BUILD_DIR)
	$(AR) rcs $@ $^

$(TEST_BIN): $(TEST_TEST_OBJS) $(TEST_SUPPORT_LIB) | $(TEST_BUILD_DIR)
	$(TEST_CXX) $(TEST_TEST_OBJS) $(TEST_SUPPORT_LIB) -o $@ $(TEST_LDFLAGS) $(LDLIBS)

clean:
	rm -f $(BIN) $(BIN_EMU) $(LIB_NATIVE) $(LIB_EMU) $(LIB_NATIVE_STATIC) $(LIB_EMU_STATIC)
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
	@test ! -d $(TEST_BUILD_DIR) || rm -rf $(TEST_BUILD_DIR)
	@# Nettoyage des traces gcov pour éviter les warnings lors des tests.
	@test ! -d $(OBJ_DIR) || find $(OBJ_DIR) -type f \( -name '*.gcda' -o -name '*.gcno' \) -delete

test-reset-counters:
	@# Keep compiled objects, reset runtime coverage counters only.
	@test ! -d $(OBJ_DIR) || find $(OBJ_DIR) -type f -name '*.gcda' -delete

ifeq ($(CPP_TEST_LOCAL),1)
test:
	@if [ "$(CPP_TEST_FORCE_REBUILD)" = "1" ]; then \
		$(MAKE) test-clean; \
	else \
		$(MAKE) test-reset-counters; \
	fi
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
		$(CPP_TEST_CCACHE_WARMUP) \
		cd executor; \
		if [ "$(CPP_TEST_FORCE_REBUILD)" = "1" ]; then \
			$(MAKE) test-clean; \
		else \
			$(MAKE) test-reset-counters; \
		fi; \
		env TEST_CXX="$(CPP_TEST_COMPILER)" $(MAKE) $(TEST_BIN) JOBS=$(CPP_TEST_JOBS); \
		$(TEST_BIN); \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID executor/$(OBJ_DIR)'
endif

build-cpp-test-image:
	@docker image inspect $(CPP_TEST_IMAGE) >/dev/null 2>&1 || \
		(echo ">> Building $(CPP_TEST_IMAGE) image (one-time setup)"; \
		 docker build -t $(CPP_TEST_IMAGE) -f $(CPP_TEST_DOCKERFILE) $(CPP_TEST_CONTEXT))

-include $(OBJS_EMU_CORE:.o=.d) \
         $(OBJS_NATIVE_CORE:.o=.d) \
         $(OBJ_MAIN:.o=.d) \
         $(TEST_OBJS:.o=.d)
