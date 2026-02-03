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
