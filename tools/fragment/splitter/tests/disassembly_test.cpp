#include <gtest/gtest.h>

#include "analysis/ObjdumpDisassembler.hpp"

using namespace splitter;

TEST(Disassembly, ParseObjdumpOutput) {
    const std::string sample =
        "0000000000001000 <demo>:\n"
        "   1000:\t48 89 d8\tmov    rax,rbx\n"
        "   1003:\tc3      \tret\n";

    auto functions = ObjdumpDisassembler::ParseOutput(sample);

    ASSERT_EQ(functions.size(), 1u);
    const Function& func = functions.front();
    EXPECT_EQ(func.Name(), "demo");
    ASSERT_EQ(func.Instructions().size(), 2u);
    EXPECT_EQ(func.Instructions()[0].Opcode(), "mov");
    EXPECT_EQ(func.Instructions()[1].Opcode(), "ret");
}
