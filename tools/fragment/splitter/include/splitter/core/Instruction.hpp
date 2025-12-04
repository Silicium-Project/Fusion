#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "splitter/support/FlatSet.hpp"

namespace splitter {

class Instruction {
public:
    uint64_t Address() const noexcept { return address_; }
    void SetAddress(uint64_t addr) noexcept { address_ = addr; }

    const std::string& Bytes() const noexcept { return bytes_; }
    void SetBytes(std::string bytes) noexcept { bytes_ = std::move(bytes); }

    const std::string& Opcode() const noexcept { return opcode_; }
    void SetOpcode(std::string opcode) noexcept { opcode_ = std::move(opcode); }

    const std::string& Operands() const noexcept { return operands_; }
    void SetOperands(std::string operands) noexcept { operands_ = std::move(operands); }

    const FlatStringSet& Reads() const noexcept { return reads_; }
    FlatStringSet& Reads() noexcept { return reads_; }

    const FlatStringSet& Writes() const noexcept { return writes_; }
    FlatStringSet& Writes() noexcept { return writes_; }

    bool IsJump() const noexcept { return is_jump_; }
    void SetIsJump(bool value) noexcept { is_jump_ = value; }

    bool IsCall() const noexcept { return is_call_; }
    void SetIsCall(bool value) noexcept { is_call_ = value; }

    bool IsMemory() const noexcept { return is_memory_; }
    void SetIsMemory(bool value) noexcept { is_memory_ = value; }

    bool WritesMemory() const noexcept { return writes_memory_; }
    void SetWritesMemory(bool value) noexcept { writes_memory_ = value; }

    const std::optional<uint64_t>& TargetAddr() const noexcept { return target_addr_; }
    void SetTargetAddr(std::optional<uint64_t> target) noexcept { target_addr_ = target; }

    [[nodiscard]] std::string ToString() const;

private:
    uint64_t address_ = 0;
    std::string bytes_;
    std::string opcode_;
    std::string operands_;
    FlatStringSet reads_;
    FlatStringSet writes_;
    bool is_jump_ = false;
    bool is_call_ = false;
    bool is_memory_ = false;
    bool writes_memory_ = false;
    std::optional<uint64_t> target_addr_;
};

}  // namespace splitter
