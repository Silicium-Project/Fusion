#include "core/Instruction.hpp"

#include <iomanip>
#include <sstream>

namespace splitter {

uint64_t Instruction::Address() const noexcept {
    return address_;
}

void Instruction::SetAddress(uint64_t addr) noexcept {
    address_ = addr;
}

const std::string& Instruction::Bytes() const noexcept {
    return bytes_;
}

void Instruction::SetBytes(std::string bytes) noexcept {
    bytes_ = std::move(bytes);
}

const std::string& Instruction::Opcode() const noexcept {
    return opcode_;
}

void Instruction::SetOpcode(std::string opcode) noexcept {
    opcode_ = std::move(opcode);
}

const std::string& Instruction::Operands() const noexcept {
    return operands_;
}

void Instruction::SetOperands(std::string operands) noexcept {
    operands_ = std::move(operands);
}

const FlatStringSet& Instruction::Reads() const noexcept {
    return reads_;
}

FlatStringSet& Instruction::Reads() noexcept {
    return reads_;
}

const FlatStringSet& Instruction::Writes() const noexcept {
    return writes_;
}

FlatStringSet& Instruction::Writes() noexcept {
    return writes_;
}

bool Instruction::IsJump() const noexcept {
    return is_jump_;
}

void Instruction::SetIsJump(bool value) noexcept {
    is_jump_ = value;
}

bool Instruction::IsCall() const noexcept {
    return is_call_;
}

void Instruction::SetIsCall(bool value) noexcept {
    is_call_ = value;
}

bool Instruction::IsMemory() const noexcept {
    return is_memory_;
}

void Instruction::SetIsMemory(bool value) noexcept {
    is_memory_ = value;
}

bool Instruction::WritesMemory() const noexcept {
    return writes_memory_;
}

void Instruction::SetWritesMemory(bool value) noexcept {
    writes_memory_ = value;
}

const std::optional<uint64_t>& Instruction::TargetAddr() const noexcept {
    return target_addr_;
}

void Instruction::SetTargetAddr(std::optional<uint64_t> target) noexcept {
    target_addr_ = target;
}

std::string Instruction::ToString() const {
    std::ostringstream oss;
    oss << "0x" << std::hex << address_ << ": " << opcode_;
    if (!operands_.empty())
        oss << " " << operands_;
    return oss.str();
}

}  // namespace splitter
