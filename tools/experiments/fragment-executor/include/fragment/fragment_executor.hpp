#pragma once

#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#include "fragment/execution_result.hpp"
#include "fragment/memory.hpp"
#include "fragment/partition_summary.hpp"

namespace fragment {

class FragmentExecutor {
public:
    explicit FragmentExecutor(bool native = false);

    void set_use_native(bool native);
    void set_binary_path(const std::string& path);
    uint64_t get_register(const std::string& reg) const;
    void set_input(const std::string& reg, uint64_t value);
    void set_inputs(const std::map<std::string, uint64_t>& inputs);

    ExecutionResult execute_safe(const std::string& asm_file);
    ExecutionResult execute_native(const std::vector<uint8_t>& binary_code);
    void print_register_state() const;

private:
    struct SegmentMapping {
        uint64_t vaddr = 0;
        uint64_t memsz = 0;
        uint64_t offset = 0;
    };

    RegisterEmulator emulator;
    bool use_native_execution;
    std::string binary_path;
    mutable bool segments_loaded;
    mutable std::vector<SegmentMapping> segments;
    mutable std::unordered_map<uint64_t, std::string> string_cache;

    std::string capture_program_stdout(const std::function<void()>& func);
    bool ensure_segments_loaded() const;
    std::string read_string_from_binary(uint64_t address) const;
    bool emulate_instruction(const std::string& line, ExecutionResult& result);
    bool emulate_mov(std::istringstream& iss, ExecutionResult& result);
    bool emulate_add(std::istringstream& iss, ExecutionResult& result);
    bool emulate_sub(std::istringstream& iss, ExecutionResult& result);
    bool emulate_xor(std::istringstream& iss, ExecutionResult& result);
    bool emulate_inc(std::istringstream& iss, ExecutionResult& result);
    bool emulate_dec(std::istringstream& iss, ExecutionResult& result);
    bool emulate_push(std::istringstream& iss, ExecutionResult& result);
    bool emulate_pop(std::istringstream& iss, ExecutionResult& result);
    bool emulate_call(std::istringstream& iss, ExecutionResult& result);
    uint64_t parse_immediate(const std::string& str) const;
    static std::string trim(const std::string& str);
};

}  // namespace fragment
