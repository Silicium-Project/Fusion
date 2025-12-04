#include <gtest/gtest.h>

#include <string>

#include "splitter/analysis/X86InstructionAnalyzer.hpp"
#include "splitter/core/Function.hpp"
#include "splitter/core/Instruction.hpp"

using namespace splitter;

TEST(InstructionAnalysis, MovReadsAndWrites) {
    const auto& analyzer = X86InstructionAnalyzer::Instance();

    Instruction inst;
    inst.SetOpcode("mov");
    inst.SetOperands("rax, rbx");
    analyzer.AnalyzeInstruction(inst);

    EXPECT_TRUE(inst.Writes().contains("rax"));
    EXPECT_TRUE(inst.Reads().contains("rbx"));
    EXPECT_FALSE(inst.IsMemory());
}

TEST(InstructionAnalysis, CallSetsTargetAndClobbers) {
    const auto& analyzer = X86InstructionAnalyzer::Instance();

    Instruction inst;
    inst.SetOpcode("call");
    inst.SetOperands("0x401000");

    analyzer.AnalyzeInstruction(inst);

    ASSERT_TRUE(inst.TargetAddr().has_value());
    EXPECT_EQ(inst.TargetAddr().value(), 0x401000u);
    EXPECT_TRUE(inst.IsCall());
    EXPECT_TRUE(inst.Writes().contains("rax"));
    EXPECT_TRUE(inst.Writes().contains("rcx"));
}

TEST(InstructionAnalysis, LoopDetectionAndPatterns) {
    const auto& analyzer = X86InstructionAnalyzer::Instance();

    Instruction loop_inst;
    loop_inst.SetAddress(0x1000);
    loop_inst.SetOpcode("jmp");
    loop_inst.SetOperands("0x1000");
    analyzer.AnalyzeInstruction(loop_inst);

    Function func;
    func.SetName("loop_func");
    func.Instructions().push_back(loop_inst);

    EXPECT_TRUE(analyzer.AnalyzeFunctionLoops(func));

    auto result = analyzer.DetectLoopPatterns(func);
    EXPECT_TRUE(result.parallelizable);
    EXPECT_FALSE(result.reason.empty());
}
