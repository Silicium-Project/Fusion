#include <gtest/gtest.h>

#include <string>

#include "splitter/instruction_analysis.hpp"
#include "splitter/types.hpp"

using namespace splitter;

TEST(InstructionAnalysis, MovReadsAndWrites) {
    AsmInstruction inst;
    inst.opcode = "mov";
    inst.operands = "rax, rbx";
    analyze_instruction(inst);

    EXPECT_TRUE(inst.writes.contains("rax"));
    EXPECT_TRUE(inst.reads.contains("rbx"));
    EXPECT_FALSE(inst.is_memory);
}

TEST(InstructionAnalysis, CallSetsTargetAndClobbers) {
    AsmInstruction inst;
    inst.opcode = "call";
    inst.operands = "0x401000";

    analyze_instruction(inst);

    ASSERT_TRUE(inst.target_addr.has_value());
    EXPECT_EQ(inst.target_addr.value(), 0x401000u);
    EXPECT_TRUE(inst.is_call);
    EXPECT_TRUE(inst.writes.contains("rax"));
    EXPECT_TRUE(inst.writes.contains("rcx"));
}

TEST(InstructionAnalysis, LoopDetectionAndPatterns) {
    AsmInstruction loop_inst;
    loop_inst.address = 0x1000;
    loop_inst.opcode = "jmp";
    loop_inst.operands = "0x1000";
    analyze_instruction(loop_inst);

    Function func;
    func.name = "loop_func";
    func.instructions.push_back(loop_inst);

    EXPECT_TRUE(analyze_function_loops(func));

    auto result = detect_loop_patterns(func);
    EXPECT_TRUE(result.parallelizable);
    EXPECT_FALSE(result.reason.empty());
}
