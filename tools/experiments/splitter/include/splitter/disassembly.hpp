#pragma once

#include <string>
#include <utility>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

    class Disassembler {
    public:
        explicit Disassembler(std::string binary_path);

        std::pair<std::vector<Function>, std::string> run() const;
        static std::vector<Function> parse_objdump_output(const std::string& output);

    private:
        std::string binary_path_;
    };

    std::vector<Function> parse_objdump_output(const std::string& output);
    std::pair<std::vector<Function>, std::string> disassemble_binary(const std::string& binary_path);

}  // namespace splitter
