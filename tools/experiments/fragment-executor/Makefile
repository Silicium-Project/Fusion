CXX := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -pedantic

BIN := fragment_executor

.PHONY: all clean

all: $(BIN)

$(BIN): fragment_executor.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

clean:
	rm -f $(BIN)
