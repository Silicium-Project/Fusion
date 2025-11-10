#pragma once

#include <algorithm>
#include <functional>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef __linux__
#include <sys/mman.h>
#include <unistd.h>
#endif

#include "fragment/execution_result.hpp"
#include "fragment/memory.hpp"

namespace fragment {

class FragmentExecutor {
private:
    RegisterEmulator emulator;
    bool use_native_execution;
    std::string binary_path;
    struct SegmentMapping {
        uint64_t vaddr = 0;
        uint64_t memsz = 0;
        uint64_t offset = 0;
    };
    std::vector<SegmentMapping> segments;
    std::vector<uint8_t> binary_data;

public:
    FragmentExecutor() : use_native_execution(false) {}
    void set_use_native(bool native) { use_native_execution = native; }
    void set_binary_path(const std::string& path) { binary_path = path; }
    uint64_t get_register(const std::string& reg) const { return emulator.get(reg); }
    void set_input(const std::string& reg, uint64_t value) { emulator.set(reg, value); }
    void set_inputs(const std::map<std::string, uint64_t>& inputs) {
        for (const auto& [reg, val] : inputs) {
            emulator.set(reg, val);
        }
    }
    ExecutionResult execute_safe(const std::string& asm_file);
    ExecutionResult execute_native(const std::vector<uint8_t>& binary_code);
    void print_register_state() const { emulator.print_state(); }

private:
    std::string capture_program_stdout(const std::function<void()>& func);
    std::string read_string_from_binary(uint64_t address) const;
    bool emulate_instruction(const std::string& line, ExecutionResult& result);
    ExecutionResult execute_binary(const PartitionInfo& partition);
    ExecutionResult execute_fragment_file(const std::string& asm_file);
    bool load_binary(const std::string& path);
    std::optional<uint64_t> resolve_symbol(const std::string& symbol) const;
};

}  // namespace fragment
