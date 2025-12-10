#include <gtest/gtest.h>

#include "analysis/InstructionAnalyzerFactory.hpp"
#include "core/Instruction.hpp"

using namespace splitter;

TEST(InstructionAnalyzerFactory, SelectsX86Analyzer) {
    auto composite = InstructionAnalyzerFactory::Create("x86_64");
    Instruction inst;
    inst.SetOpcode("jmp");
    inst.SetOperands("0x10");
    composite.AnalyzeInstruction(inst);
    EXPECT_TRUE(inst.IsJump());
}

TEST(InstructionAnalyzerFactory, GenericAnalyzerDoesNotMarkJump) {
    auto composite = InstructionAnalyzerFactory::Create("generic");
    Instruction inst;
    inst.SetOpcode("jmp");
    composite.AnalyzeInstruction(inst);
    EXPECT_FALSE(inst.IsJump());
}

TEST(InstructionAnalyzerFactory, MatchesObjdumpArchString) {
    auto composite = InstructionAnalyzerFactory::Create("i386:x86-64");
    Instruction inst;
    inst.SetOpcode("jmp");
    inst.SetOperands("0x10");
    composite.AnalyzeInstruction(inst);
    EXPECT_TRUE(inst.IsJump());
}
