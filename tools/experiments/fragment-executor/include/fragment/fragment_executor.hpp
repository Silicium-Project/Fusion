#pragma once

#include "fragment/common.hpp"
#include "fragment/config.hpp"
#include "fragment/execution_result.hpp"
#include "fragment/memory.hpp"
#include "fragment/opcodes.hpp"
#include "fragment/instruction_emulator.hpp"
#include "fragment/segment_loader.hpp"
#include "fragment/partition_summary.hpp"

namespace fragment {

class FragmentExecutor {
public:
    explicit FragmentExecutor(ExecutorConfig config = {});

    void set_use_native(bool native);
    void set_binary_path(const std::string& path);
    uint64_t get_register(const std::string& reg) const;
    void set_input(const std::string& reg, uint64_t value);
    void set_inputs(const std::map<std::string, uint64_t>& inputs);

    ExecutionResult execute_safe(const std::string& asm_file);
    ExecutionResult execute_native(const std::vector<uint8_t>& binary_code);
    void print_register_state() const;

private:
    RegisterEmulator emulator;
    ExecutorConfig config_;
    SegmentLoader segment_loader_;
    InstructionEmulator instruction_emulator_;

    std::string capture_program_stdout(const std::function<void()>& func);
    bool emulate_instruction(const std::string& line, ExecutionResult& result);
    bool emulate_call(std::istringstream& iss, ExecutionResult& result);
    std::optional<std::string> read_string_from_binary(uint64_t address) const;
};

}  // namespace fragment
