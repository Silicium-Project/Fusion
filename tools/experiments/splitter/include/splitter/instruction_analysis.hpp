#pragma once

#include <map>
#include <string>
#include <string_view>

#include "splitter/types.hpp"

namespace splitter {

    bool is_jump_opcode(std::string_view opcode);
    bool is_call_opcode(std::string_view opcode);
    bool is_stack_opcode(std::string_view opcode);
    bool is_call_clobbered_reg(std::string_view reg);

    void analyze_instruction(AsmInstruction& inst);
    bool analyze_function_loops(Function& func);
    std::map<std::string, std::string> detect_loop_patterns(const Function& func);

}  // namespace splitter
