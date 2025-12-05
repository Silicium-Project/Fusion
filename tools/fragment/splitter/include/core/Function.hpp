#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "core/Instruction.hpp"
#include "core/LoopInfo.hpp"

namespace splitter {

class Function {
public:
    const std::string& Name() const noexcept { return name_; }
    void SetName(std::string name) noexcept { name_ = std::move(name); }

    uint64_t StartAddr() const noexcept { return start_addr_; }
    void SetStartAddr(uint64_t addr) noexcept { start_addr_ = addr; }

    uint64_t EndAddr() const noexcept { return end_addr_; }
    void SetEndAddr(uint64_t addr) noexcept { end_addr_ = addr; }

    const std::vector<Instruction>& Instructions() const noexcept { return instructions_; }
    std::vector<Instruction>& Instructions() noexcept { return instructions_; }

    bool IsLoop() const noexcept { return is_loop_; }
    void SetIsLoop(bool value) noexcept { is_loop_ = value; }

    const std::vector<LoopInfo>& Loops() const noexcept { return loops_; }
    std::vector<LoopInfo>& Loops() noexcept { return loops_; }

private:
    std::string name_;
    uint64_t start_addr_ = 0;
    uint64_t end_addr_ = 0;
    std::vector<Instruction> instructions_;
    bool is_loop_ = false;
    std::vector<LoopInfo> loops_;
};

}  // namespace splitter
