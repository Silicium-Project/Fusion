#include <optional>
#include <string>

#include <gtest/gtest.h>

#include "core/PrintfEmulator.hpp"

TEST(PrintfEmulator, FormatsRegistersAndStackArgs) {
    fragment::PrintfArgs args;
    args.regs = {1, 2, 3, 4, 5};
    args.stack = {6, 7};

    auto out = fragment::format_printf_like(
        "%d %d %d %d %d %d %d",
        args,
        [](uint64_t) { return std::optional<std::string>{}; });

    EXPECT_EQ(out, "1 2 3 4 5 6 7");
}

TEST(PrintfEmulator, HandlesStringArgument) {
    fragment::PrintfArgs args;
    args.regs = {0x1000, 0, 0, 0, 0};

    auto out = fragment::format_printf_like(
        "msg:%s",
        args,
        [](uint64_t addr) -> std::optional<std::string> {
            if (addr == 0x1000)
                return std::string("hello");
            return std::nullopt;
        });

    EXPECT_EQ(out, "msg:hello");
}

TEST(PrintfEmulator, AppliesPrecisionAndZeroPadding) {
    fragment::PrintfArgs args;
    args.regs = {0x1000, 0xAu, 0, 0, 0};

    auto out = fragment::format_printf_like(
        "%.3s %04x",
        args,
        [](uint64_t addr) -> std::optional<std::string> {
            if (addr == 0x1000)
                return std::string("hello");
            return std::nullopt;
        });

    EXPECT_EQ(out, "hel 000a");
}

TEST(PrintfEmulator, GatherArgsSystemVProfile) {
    fragment::RegisterEmulator emulator;
    emulator.set("rdi", 0x1111);
    emulator.set("rsi", 1);
    emulator.set("rdx", 2);
    emulator.set("rcx", 3);
    emulator.set("r8", 4);
    emulator.set("r9", 5);
    emulator.set("rsp", 0x8000);
    emulator.write_qword(0x8000, 6);
    emulator.write_qword(0x8008, 7);

    const auto args = fragment::gather_printf_args(emulator, fragment::AbiProfile::SystemV, 2);
    EXPECT_EQ(args.fmt, 0x1111u);
    EXPECT_EQ(args.regs[0], 1u);
    EXPECT_EQ(args.regs[1], 2u);
    EXPECT_EQ(args.regs[2], 3u);
    EXPECT_EQ(args.regs[3], 4u);
    EXPECT_EQ(args.regs[4], 5u);
    EXPECT_EQ(args.stack[0], 6u);
    EXPECT_EQ(args.stack[1], 7u);
}

TEST(PrintfEmulator, GatherArgsWindowsX64Profile) {
    fragment::RegisterEmulator emulator;
    emulator.set("rcx", 0x2222);
    emulator.set("rdx", 11);
    emulator.set("r8", 12);
    emulator.set("r9", 13);
    emulator.set("rsp", 0x9000);
    emulator.write_qword(0x9028, 14);
    emulator.write_qword(0x9030, 15);
    emulator.write_qword(0x9038, 16);
    emulator.write_qword(0x9040, 17);

    const auto args = fragment::gather_printf_args(emulator, fragment::AbiProfile::WindowsX64, 2);
    EXPECT_EQ(args.fmt, 0x2222u);
    EXPECT_EQ(args.regs[0], 11u);
    EXPECT_EQ(args.regs[1], 12u);
    EXPECT_EQ(args.regs[2], 13u);
    EXPECT_EQ(args.regs[3], 14u);
    EXPECT_EQ(args.regs[4], 15u);
    EXPECT_EQ(args.stack[0], 16u);
    EXPECT_EQ(args.stack[1], 17u);
}
