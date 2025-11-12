#include <gtest/gtest.h>

#include "splitter/disassembly.hpp"

using namespace splitter;

TEST(Disassembly, ParseObjdumpOutput) {
    const std::string sample =
        "0000000000001000 <demo>:\n"
        "   1000:\t48 89 d8\tmov    rax,rbx\n"
        "   1003:\tc3      \tret\n";

    auto functions = parse_objdump_output(sample);

    ASSERT_EQ(functions.size(), 1u);
    const Function& func = functions.front();
    EXPECT_EQ(func.name, "demo");
    ASSERT_EQ(func.instructions.size(), 2u);
    EXPECT_EQ(func.instructions[0].opcode, "mov");
    EXPECT_EQ(func.instructions[1].opcode, "ret");
}

