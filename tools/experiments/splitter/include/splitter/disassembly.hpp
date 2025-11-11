#pragma once

#include <string>
#include <utility>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

    std::vector<Function> parse_objdump_output(const std::string& output);
    std::pair<std::vector<Function>, std::string> disassemble_binary(const std::string& binary_path);

}  // namespace splitter
