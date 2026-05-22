#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "analysis/LoopAnalysis.hpp"
#include "core/Instruction.hpp"
#include "core/LoopInfo.hpp"

namespace splitter {

class Function {
public:
    const std::string& Name() const noexcept;
    void SetName(std::string name) noexcept;

    uint64_t StartAddr() const noexcept;
    void SetStartAddr(uint64_t addr) noexcept;

    uint64_t EndAddr() const noexcept;
    void SetEndAddr(uint64_t addr) noexcept;

    const std::vector<Instruction>& Instructions() const noexcept;
    std::vector<Instruction>& Instructions() noexcept;

    bool IsLoop() const noexcept;
    void SetIsLoop(bool value) noexcept;

    const std::vector<LoopInfo>& Loops() const noexcept;
    std::vector<LoopInfo>& Loops() noexcept;

    const std::optional<LoopAnalysis>& LoopAnalysisInfo() const noexcept;
    void SetLoopAnalysis(LoopAnalysis info);
    bool HasLoopAnalysis() const noexcept;

private:
    std::string name_;
    uint64_t start_addr_ = 0;
    uint64_t end_addr_ = 0;
    std::vector<Instruction> instructions_;
    bool is_loop_ = false;
    std::vector<LoopInfo> loops_;
    std::optional<LoopAnalysis> loop_analysis_;
};

}  // namespace splitter
