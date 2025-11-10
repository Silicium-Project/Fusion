#pragma once

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace splitter {

struct AsmInstruction {
    uint64_t address = 0;
    std::string bytes;
    std::string opcode;
    std::string operands;
    std::set<std::string> reads;
    std::set<std::string> writes;
    bool is_jump = false;
    bool is_call = false;
    bool is_memory = false;
    std::optional<uint64_t> target_addr;

    std::string to_string() const;
};

struct Function {
    std::string name;
    uint64_t start_addr = 0;
    uint64_t end_addr = 0;
    std::vector<AsmInstruction> instructions;
    bool is_loop = false;
};

struct BinaryPartition {
    std::string id;
    std::vector<Function> functions;
    uint64_t start_addr = 0;
    uint64_t end_addr = 0;
    std::string asm_code;
    std::vector<uint8_t> raw_bytes;
    std::set<std::string> inputs;
    std::set<std::string> outputs;
    bool is_parallelizable = false;
    std::vector<std::string> dependencies;
    std::vector<std::string> parents;
    std::set<std::string> external_inputs;
    std::vector<std::string> unresolved_dependencies;
};

struct PartitionFiles {
    std::string asm_file;
    std::string bin_file;
    std::string wrapper_file;
};

}  // namespace splitter
