#pragma once

#include "fragment/common.hpp"

namespace fragment {

enum class Opcode {
    Mov,
    Add,
    Sub,
    Xor,
    Inc,
    Dec,
    Push,
    Pop,
    Call,
    Ret,
    Nop,
    Unknown
};

inline Opcode classify_opcode(std::string_view mnemonic) {
    static const std::array<std::pair<std::string_view, Opcode>, 15> kMap = {{
        {"mov", Opcode::Mov},   {"movq", Opcode::Mov},   {"movl", Opcode::Mov},
        {"add", Opcode::Add},   {"addq", Opcode::Add},   {"addl", Opcode::Add},
        {"sub", Opcode::Sub},   {"subq", Opcode::Sub},   {"subl", Opcode::Sub},
        {"xor", Opcode::Xor},   {"xorq", Opcode::Xor},   {"xorl", Opcode::Xor},
        {"inc", Opcode::Inc},   {"incq", Opcode::Inc},   {"incl", Opcode::Inc},
    }};

    auto lower = mnemonic;
    std::string normalized(lower);
    std::transform(normalized.begin(), normalized.end(), normalized.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });

    for (const auto& [token, op] : kMap)
        if (normalized == token)
            return op;

    if (normalized == "dec" || normalized == "decq" || normalized == "decl")
        return Opcode::Dec;
    if (normalized == "push" || normalized == "pushq")
        return Opcode::Push;
    if (normalized == "pop" || normalized == "popq")
        return Opcode::Pop;
    if (normalized == "call" || normalized == "callq")
        return Opcode::Call;
    if (normalized == "ret" || normalized == "retq")
        return Opcode::Ret;
    if (normalized == "nop")
        return Opcode::Nop;

    return Opcode::Unknown;
}

}  // namespace fragment
