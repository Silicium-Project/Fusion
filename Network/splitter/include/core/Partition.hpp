#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "core/Function.hpp"
#include "support/FlatSet.hpp"

namespace splitter {

class Partition {
public:
    const std::string& Id() const noexcept;
    void SetId(std::string id) noexcept;

    const std::vector<Function>& Functions() const noexcept;
    std::vector<Function>& Functions() noexcept;

    uint64_t StartAddr() const noexcept;
    void SetStartAddr(uint64_t addr) noexcept;

    uint64_t EndAddr() const noexcept;
    void SetEndAddr(uint64_t addr) noexcept;

    const std::string& AsmCode() const noexcept;
    void SetAsmCode(std::string code) noexcept;

    const std::vector<uint8_t>& RawBytes() const noexcept;
    std::vector<uint8_t>& RawBytes() noexcept;

    const std::string& BinHash() const noexcept;
    void SetBinHash(std::string hash) noexcept;

    const std::string& PartitionHash() const noexcept;
    void SetPartitionHash(std::string hash) noexcept;

    const FlatStringSet& Inputs() const noexcept;
    FlatStringSet& Inputs() noexcept;

    const FlatStringSet& Outputs() const noexcept;
    FlatStringSet& Outputs() noexcept;

    bool IsParallelizable() const noexcept;
    void SetIsParallelizable(bool value) noexcept;

    const std::vector<std::string>& Dependencies() const noexcept;
    std::vector<std::string>& Dependencies() noexcept;

    const std::vector<std::string>& Parents() const noexcept;
    std::vector<std::string>& Parents() noexcept;

    const FlatStringSet& ExternalInputs() const noexcept;
    FlatStringSet& ExternalInputs() noexcept;

    const std::vector<std::string>& UnresolvedDependencies() const noexcept;
    std::vector<std::string>& UnresolvedDependencies() noexcept;

    bool RequiresDisplay() const noexcept;
    void SetRequiresDisplay(bool value) noexcept;

    const FlatStringSet& ExternalCalls() const noexcept;
    FlatStringSet& ExternalCalls() noexcept;

private:
    std::string id_;
    std::vector<Function> functions_;
    uint64_t start_addr_ = 0;
    uint64_t end_addr_ = 0;
    std::string asm_code_;
    std::vector<uint8_t> raw_bytes_;
    std::string bin_hash_;
    std::string partition_hash_;
    FlatStringSet inputs_;
    FlatStringSet outputs_;
    bool is_parallelizable_ = false;
    std::vector<std::string> dependencies_;
    std::vector<std::string> parents_;
    FlatStringSet external_inputs_;
    std::vector<std::string> unresolved_dependencies_;
    bool requires_display_ = false;
    FlatStringSet external_calls_;
};

}  // namespace splitter
