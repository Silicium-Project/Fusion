#pragma once

#include "core/Memory.hpp"

#include <array>
#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace fragment {

struct PrintfArgs {
    uint64_t fmt = 0;
    std::array<uint64_t, 5> regs{};  // rsi, rdx, rcx, r8, r9
    std::vector<uint64_t> stack;
};

using ReadStringFunc = std::function<std::optional<std::string>(uint64_t)>;

PrintfArgs gather_printf_args(const RegisterEmulator& emulator, std::size_t max_stack_args = 16);
std::string format_printf_like(const std::string& fmt, const PrintfArgs& args, const ReadStringFunc& read_string);

}  // namespace fragment
