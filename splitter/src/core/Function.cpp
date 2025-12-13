#include "core/Function.hpp"

namespace splitter {

const std::string& Function::Name() const noexcept {
    return name_;
}

void Function::SetName(std::string name) noexcept {
    name_ = std::move(name);
}

uint64_t Function::StartAddr() const noexcept {
    return start_addr_;
}

void Function::SetStartAddr(uint64_t addr) noexcept {
    start_addr_ = addr;
}

uint64_t Function::EndAddr() const noexcept {
    return end_addr_;
}

void Function::SetEndAddr(uint64_t addr) noexcept {
    end_addr_ = addr;
}

const std::vector<Instruction>& Function::Instructions() const noexcept {
    return instructions_;
}

std::vector<Instruction>& Function::Instructions() noexcept {
    return instructions_;
}

bool Function::IsLoop() const noexcept {
    return is_loop_;
}

void Function::SetIsLoop(bool value) noexcept {
    is_loop_ = value;
}

const std::vector<LoopInfo>& Function::Loops() const noexcept {
    return loops_;
}

std::vector<LoopInfo>& Function::Loops() noexcept {
    return loops_;
}

}  // namespace splitter
