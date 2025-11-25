#pragma once

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "splitter/containers.hpp"

namespace splitter {

    struct LoopDescriptor {
        uint64_t source_addr = 0;
        uint64_t target_addr = 0;
        bool backward = false;
    };

    struct AsmInstruction {
        uint64_t address = 0;
        std::string bytes;
        std::string opcode;
        std::string operands;
        FlatStringSet reads;
        FlatStringSet writes;
        bool is_jump = false;
        bool is_call = false;
        bool is_memory = false;
        bool writes_memory = false;
        std::optional<uint64_t> target_addr;

        std::string to_string() const;
    };

    struct Function {
        std::string name;
        uint64_t start_addr = 0;
        uint64_t end_addr = 0;
        std::vector<AsmInstruction> instructions;
        bool is_loop = false;
        std::vector<LoopDescriptor> loops;
    };

    struct BinaryPartition {
        std::string id;
        std::vector<Function> functions;
        uint64_t start_addr = 0;
        uint64_t end_addr = 0;
        std::string asm_code;
        std::vector<uint8_t> raw_bytes;
        std::string bin_hash;
        std::set<std::string> inputs;
        std::set<std::string> outputs;
        bool is_parallelizable = false;
        std::vector<std::string> dependencies;
        std::vector<std::string> parents;
        std::set<std::string> external_inputs;
        std::vector<std::string> unresolved_dependencies;
        bool requires_display = false;
        std::set<std::string> external_calls;
    };

struct PartitionFiles {
    std::string asm_file;
    std::string bin_file;
    std::string wrapper_file;
};

struct MemorySegment {
    std::string name;
    uint64_t address = 0;
    std::vector<uint8_t> bytes;
};

struct LibraryInfo {
    std::string name;
    std::string path;
    std::string soname;
    std::string build_id;
};

struct PartitionSummary {
    std::string binary_path;
    std::string binary_hash;
    bool can_split = true;
    std::vector<std::string> required_libraries;
    std::vector<LibraryInfo> libraries;
    std::vector<BinaryPartition> partitions;
    std::vector<MemorySegment> initial_memory;
};

}  // namespace splitter
