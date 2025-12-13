#include "core/Partition.hpp"

namespace splitter {

const std::string& Partition::Id() const noexcept {
    return id_;
}

void Partition::SetId(std::string id) noexcept {
    id_ = std::move(id);
}

const std::vector<Function>& Partition::Functions() const noexcept {
    return functions_;
}

std::vector<Function>& Partition::Functions() noexcept {
    return functions_;
}

uint64_t Partition::StartAddr() const noexcept {
    return start_addr_;
}

void Partition::SetStartAddr(uint64_t addr) noexcept {
    start_addr_ = addr;
}

uint64_t Partition::EndAddr() const noexcept {
    return end_addr_;
}

void Partition::SetEndAddr(uint64_t addr) noexcept {
    end_addr_ = addr;
}

const std::string& Partition::AsmCode() const noexcept {
    return asm_code_;
}

void Partition::SetAsmCode(std::string code) noexcept {
    asm_code_ = std::move(code);
}

const std::vector<uint8_t>& Partition::RawBytes() const noexcept {
    return raw_bytes_;
}

std::vector<uint8_t>& Partition::RawBytes() noexcept {
    return raw_bytes_;
}

const std::string& Partition::BinHash() const noexcept {
    return bin_hash_;
}

void Partition::SetBinHash(std::string hash) noexcept {
    bin_hash_ = std::move(hash);
}

const std::string& Partition::PartitionHash() const noexcept {
    return partition_hash_;
}

void Partition::SetPartitionHash(std::string hash) noexcept {
    partition_hash_ = std::move(hash);
}

const FlatStringSet& Partition::Inputs() const noexcept {
    return inputs_;
}

FlatStringSet& Partition::Inputs() noexcept {
    return inputs_;
}

const FlatStringSet& Partition::Outputs() const noexcept {
    return outputs_;
}

FlatStringSet& Partition::Outputs() noexcept {
    return outputs_;
}

bool Partition::IsParallelizable() const noexcept {
    return is_parallelizable_;
}

void Partition::SetIsParallelizable(bool value) noexcept {
    is_parallelizable_ = value;
}

const std::vector<std::string>& Partition::Dependencies() const noexcept {
    return dependencies_;
}

std::vector<std::string>& Partition::Dependencies() noexcept {
    return dependencies_;
}

const std::vector<std::string>& Partition::Parents() const noexcept {
    return parents_;
}

std::vector<std::string>& Partition::Parents() noexcept {
    return parents_;
}

const FlatStringSet& Partition::ExternalInputs() const noexcept {
    return external_inputs_;
}

FlatStringSet& Partition::ExternalInputs() noexcept {
    return external_inputs_;
}

const std::vector<std::string>& Partition::UnresolvedDependencies() const noexcept {
    return unresolved_dependencies_;
}

std::vector<std::string>& Partition::UnresolvedDependencies() noexcept {
    return unresolved_dependencies_;
}

bool Partition::RequiresDisplay() const noexcept {
    return requires_display_;
}

void Partition::SetRequiresDisplay(bool value) noexcept {
    requires_display_ = value;
}

const FlatStringSet& Partition::ExternalCalls() const noexcept {
    return external_calls_;
}

FlatStringSet& Partition::ExternalCalls() noexcept {
    return external_calls_;
}

}  // namespace splitter
