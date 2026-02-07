#include <gtest/gtest.h>

#include "core/Opcodes.hpp"

using fragment::Opcode;
using fragment::classify_opcode;

TEST(Opcode, NormalizeVariants) {
    EXPECT_EQ(classify_opcode("mov"), Opcode::Mov);
    EXPECT_EQ(classify_opcode("MOVQ"), Opcode::Mov);
    EXPECT_EQ(classify_opcode("addl"), Opcode::Add);
    EXPECT_EQ(classify_opcode("subq"), Opcode::Sub);
    EXPECT_EQ(classify_opcode("inc"), Opcode::Inc);
    EXPECT_EQ(classify_opcode("pushq"), Opcode::Push);
    EXPECT_EQ(classify_opcode("call"), Opcode::Call);
    EXPECT_EQ(classify_opcode("retq"), Opcode::Ret);
    EXPECT_EQ(classify_opcode("nop"), Opcode::Nop);
    EXPECT_EQ(classify_opcode("unknown"), Opcode::Unknown);
}

