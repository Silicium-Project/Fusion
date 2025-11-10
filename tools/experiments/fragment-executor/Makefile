CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic
CPPFLAGS := -Iinclude

SRC_DIR := src
OBJ_DIR := build
BIN := fragment_executor

SRC := $(wildcard $(SRC_DIR)/*.cpp)
OBJS := $(patsubst $(SRC_DIR)/%.cpp,$(OBJ_DIR)/%.o,$(SRC))

.PHONY: all clean

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
