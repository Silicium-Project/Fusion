#pragma once

#include <map>
#include <string>

#include "splitter/types.hpp"

namespace splitter {

void analyze_instruction(AsmInstruction& inst);
bool analyze_function_loops(Function& func);
std::map<std::string, std::string> detect_loop_patterns(const Function& func);

}  // namespace splitter
