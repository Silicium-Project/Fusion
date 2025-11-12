CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic
CPPFLAGS := -Iinclude

SRC_DIR := src
OBJ_DIR := build
BIN := fragment_executor

SRC := $(wildcard $(SRC_DIR)/*.cpp)
OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(OBJ_DIR)/%.o,$(SRC))

TEST_SRCS := tests/config_test.cpp tests/opcode_test.cpp tests/executor_test.cpp tests/instruction_emulator_test.cpp
TEST_EXTRA_SRCS := src/fragment_executor.cpp src/register_emulator.cpp src/utils.cpp src/logging.cpp src/execution_result.cpp src/instruction_emulator.cpp src/segment_loader.cpp
TEST_BUILD_DIR := $(OBJ_DIR)/tests
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

.PHONY: all clean test

all: $(BIN)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BIN): $(OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@

clean:
	rm -f $(BIN)
	rm -rf $(OBJ_DIR)

test:
	docker run --rm \
		-e HOST_UID=$(HOST_UID) -e HOST_GID=$(HOST_GID) \
		-v $(abspath ../../..):/workspace:Z -w /workspace \
		debian:bookworm-slim bash -lc '\
		set -euo pipefail; \
		apt-get update >/dev/null && apt-get install -y --no-install-recommends build-essential cmake libgtest-dev >/dev/null; \
		cmake -S /usr/src/googletest -B /tmp/gtest >/dev/null && cmake --build /tmp/gtest >/dev/null && cmake --install /tmp/gtest >/dev/null; \
		cd tools/experiments/fragment-executor; \
		rm -rf $(TEST_BUILD_DIR) && mkdir -p $(TEST_BUILD_DIR); \
		g++ -Iinclude -std=c++17 -O2 -Wall -Wextra -pedantic --coverage \
			$(TEST_SRCS) $(TEST_EXTRA_SRCS) \
			-o $(TEST_BUILD_DIR)/fragment_tests --coverage -lgtest -lgtest_main -pthread; \
		$(TEST_BUILD_DIR)/fragment_tests; \
		cd /workspace && chown -R $$HOST_UID:$$HOST_GID tools/experiments/fragment-executor/$(OBJ_DIR)'
