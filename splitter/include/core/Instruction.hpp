#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "support/FlatSet.hpp"

namespace splitter {

class Instruction {
public:
    uint64_t Address() const noexcept;
    void SetAddress(uint64_t addr) noexcept;

    const std::string& Bytes() const noexcept;
    void SetBytes(std::string bytes) noexcept;

    const std::string& Opcode() const noexcept;
    void SetOpcode(std::string opcode) noexcept;

    const std::string& Operands() const noexcept;
    void SetOperands(std::string operands) noexcept;

    const FlatStringSet& Reads() const noexcept;
    FlatStringSet& Reads() noexcept;

    const FlatStringSet& Writes() const noexcept;
    FlatStringSet& Writes() noexcept;

    bool IsJump() const noexcept;
    void SetIsJump(bool value) noexcept;

    bool IsCall() const noexcept;
    void SetIsCall(bool value) noexcept;

    bool IsMemory() const noexcept;
    void SetIsMemory(bool value) noexcept;

    bool WritesMemory() const noexcept;
    void SetWritesMemory(bool value) noexcept;

    const std::optional<uint64_t>& TargetAddr() const noexcept;
    void SetTargetAddr(std::optional<uint64_t> target) noexcept;

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
