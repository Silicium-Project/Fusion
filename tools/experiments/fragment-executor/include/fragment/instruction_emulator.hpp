#pragma once

#include "fragment/common.hpp"
#include "fragment/execution_result.hpp"
#include "fragment/memory.hpp"
#include "fragment/opcodes.hpp"

namespace fragment {

class InstructionEmulator {
public:
    explicit InstructionEmulator(RegisterEmulator& emulator);

    bool emulate_line(const std::string& line, ExecutionResult& result);

private:
    RegisterEmulator& emulator_;

    bool emulate_mov(std::istringstream& iss, ExecutionResult& result);
    bool emulate_binary_op(std::istringstream& iss, ExecutionResult& result, Opcode opcode);
    bool emulate_xor(std::istringstream& iss, ExecutionResult& result);
    bool emulate_inc(std::istringstream& iss);
    bool emulate_dec(std::istringstream& iss);
    bool emulate_push(std::istringstream& iss, ExecutionResult& result);
    bool emulate_pop(std::istringstream& iss, ExecutionResult& result);

    uint64_t parse_immediate(const std::string& token) const;
    std::string trim(const std::string& token) const;
};

}  // namespace fragment
