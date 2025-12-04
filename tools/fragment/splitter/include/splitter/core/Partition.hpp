#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <vector>

#include "splitter/core/Function.hpp"
#include "splitter/support/FlatStringSet.hpp"

namespace splitter {

class Partition {
public:
    const std::string& Id() const noexcept { return id_; }
    void SetId(std::string id) noexcept { id_ = std::move(id); }

    const std::vector<Function>& Functions() const noexcept { return functions_; }
    std::vector<Function>& Functions() noexcept { return functions_; }

    uint64_t StartAddr() const noexcept { return start_addr_; }
    void SetStartAddr(uint64_t addr) noexcept { start_addr_ = addr; }

    uint64_t EndAddr() const noexcept { return end_addr_; }
    void SetEndAddr(uint64_t addr) noexcept { end_addr_ = addr; }

    const std::string& AsmCode() const noexcept { return asm_code_; }
    void SetAsmCode(std::string code) noexcept { asm_code_ = std::move(code); }

    const std::vector<uint8_t>& RawBytes() const noexcept { return raw_bytes_; }
    std::vector<uint8_t>& RawBytes() noexcept { return raw_bytes_; }

    const std::string& BinHash() const noexcept { return bin_hash_; }
    void SetBinHash(std::string hash) noexcept { bin_hash_ = std::move(hash); }

    const std::string& PartitionHash() const noexcept { return partition_hash_; }
    void SetPartitionHash(std::string hash) noexcept { partition_hash_ = std::move(hash); }

    const std::set<std::string>& Inputs() const noexcept { return inputs_; }
    std::set<std::string>& Inputs() noexcept { return inputs_; }

    const std::set<std::string>& Outputs() const noexcept { return outputs_; }
    std::set<std::string>& Outputs() noexcept { return outputs_; }

    bool IsParallelizable() const noexcept { return is_parallelizable_; }
    void SetIsParallelizable(bool value) noexcept { is_parallelizable_ = value; }

    const std::vector<std::string>& Dependencies() const noexcept { return dependencies_; }
    std::vector<std::string>& Dependencies() noexcept { return dependencies_; }

    const std::vector<std::string>& Parents() const noexcept { return parents_; }
    std::vector<std::string>& Parents() noexcept { return parents_; }

    const std::set<std::string>& ExternalInputs() const noexcept { return external_inputs_; }
    std::set<std::string>& ExternalInputs() noexcept { return external_inputs_; }

    const std::vector<std::string>& UnresolvedDependencies() const noexcept { return unresolved_dependencies_; }
    std::vector<std::string>& UnresolvedDependencies() noexcept { return unresolved_dependencies_; }

    bool RequiresDisplay() const noexcept { return requires_display_; }
    void SetRequiresDisplay(bool value) noexcept { requires_display_ = value; }

    const std::set<std::string>& ExternalCalls() const noexcept { return external_calls_; }
    std::set<std::string>& ExternalCalls() noexcept { return external_calls_; }

private:
    std::string id_;
    std::vector<Function> functions_;
    uint64_t start_addr_ = 0;
    uint64_t end_addr_ = 0;
    std::string asm_code_;
    std::vector<uint8_t> raw_bytes_;
    std::string bin_hash_;
    std::string partition_hash_;
    std::set<std::string> inputs_;
    std::set<std::string> outputs_;
    bool is_parallelizable_ = false;
    std::vector<std::string> dependencies_;
    std::vector<std::string> parents_;
    std::set<std::string> external_inputs_;
    std::vector<std::string> unresolved_dependencies_;
    bool requires_display_ = false;
    std::set<std::string> external_calls_;
};

}  // namespace splitter
