#pragma once

#include "fragment/common.hpp"
#include "fragment/memory.hpp"

namespace fragment {

struct ExecutionResult {
    bool success = false;
    std::string error_message;
    std::map<std::string, uint64_t> initial_regs;
    std::map<std::string, uint64_t> final_regs;
    std::map<std::string, std::pair<uint64_t, uint64_t>> changed_regs;
    size_t instructions_executed = 0;
    size_t memory_accesses = 0;
    std::string program_stdout;
    std::vector<MemoryPatch> memory_patches;

    void print() const;
};

}  // namespace fragment
