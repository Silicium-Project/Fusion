#pragma once

#include <memory>
#include <string_view>

#include "splitter/analysis/IInstructionAnalyzer.hpp"

namespace splitter {

class X86InstructionAnalyzer : public IInstructionAnalyzer {
public:
    static const X86InstructionAnalyzer& Instance();

    void AnalyzeInstruction(Instruction& inst) const override;
    bool AnalyzeFunctionLoops(Function& func) const override;
    LoopAnalysis DetectLoopPatterns(const Function& func) const override;

    static bool IsJumpOpcode(std::string_view opcode);
    static bool IsCallOpcode(std::string_view opcode);
    static bool IsStackOpcode(std::string_view opcode);
    static bool IsCallClobberedReg(std::string_view reg);

private:
    X86InstructionAnalyzer() = default;
};

}  // namespace splitter
