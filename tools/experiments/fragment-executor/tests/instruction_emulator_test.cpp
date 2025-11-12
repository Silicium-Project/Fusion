#include <gtest/gtest.h>

#include "fragment/instruction_emulator.hpp"
#include "fragment/memory.hpp"

using fragment::ExecutionResult;
using fragment::InstructionEmulator;
using fragment::RegisterEmulator;

TEST(InstructionEmulator, BasicArithmetic) {
    RegisterEmulator regs;
    InstructionEmulator emu(regs);
    ExecutionResult result;

    regs.set("rbx", 5);
    ASSERT_TRUE(emu.emulate_line("1000: add rbx, $3", result));
    EXPECT_EQ(regs.get("rbx"), 8u);

    ASSERT_TRUE(emu.emulate_line("1001: sub rbx, $2", result));
    EXPECT_EQ(regs.get("rbx"), 6u);
}

TEST(InstructionEmulator, StackOperations) {
    RegisterEmulator regs;
    InstructionEmulator emu(regs);
    ExecutionResult result;

    regs.set("rax", 42);
    ASSERT_TRUE(emu.emulate_line("2000: push rax", result));
    ASSERT_TRUE(emu.emulate_line("2008: pop rbx", result));

    EXPECT_EQ(regs.get("rbx"), 42u);
}

