#include <gtest/gtest.h>

#include "InstructionEmulator.hpp"
#include "Memory.hpp"

using fragment::ExecutionResult;
using fragment::InstructionEmulator;
using fragment::PatchLogGuard;
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

TEST(InstructionEmulator, MovabsWritesFullQwordToMemory) {
    RegisterEmulator regs;
    ExecutionResult result;
    PatchLogGuard guard(regs, result.memory_patches);
    InstructionEmulator emu(regs);

    constexpr uint64_t addr = 0x5000;
    constexpr uint64_t value = 0x1122334455667788ULL;
    ASSERT_TRUE(emu.emulate_line("0000000000002000: movabs QWORD PTR [0x5000], $0x1122334455667788", result));

    EXPECT_EQ(regs.read_qword(addr), value);
    ASSERT_EQ(result.memory_patches.size(), 1u);
    EXPECT_EQ(result.memory_patches.front().address, addr);
    EXPECT_EQ(result.memory_patches.front().after.size(), 8u);
}

TEST(InstructionEmulator, MovUsesDeclaredMemoryWidth) {
    RegisterEmulator regs;
    ExecutionResult result;
    PatchLogGuard guard(regs, result.memory_patches);
    InstructionEmulator emu(regs);

    // Positionner la base pile pour un accès [rbp - offset]
    regs.set("rbp", 0x8000);

    ASSERT_TRUE(emu.emulate_line("0000000000003000: mov qword ptr [rbp-0x8], $0x5566778899AABBCC", result));
    EXPECT_EQ(regs.read_qword(0x8000 - 0x8), 0x5566778899AABBCCULL);

    ASSERT_TRUE(emu.emulate_line("0000000000003008: mov word ptr [rbp-0x6], $0x1234", result));

    auto bytes = regs.read_bytes(0x8000 - 0x8, 8);
    ASSERT_EQ(bytes.size(), 8u);
    // Vérifie que seuls deux octets ont été écrasés.
    const std::array<uint8_t, 8> expected = {0xCC, 0xBB, 0x34, 0x12, 0x88, 0x77, 0x66, 0x55};
    EXPECT_TRUE(std::equal(bytes.begin(), bytes.end(), expected.begin(), expected.end()));
    ASSERT_EQ(result.memory_patches.size(), 2u);
    EXPECT_EQ(result.memory_patches.back().after.size(), 2u);
}
