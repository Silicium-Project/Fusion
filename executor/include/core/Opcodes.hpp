#pragma once

#include "core/Common.hpp"

namespace fragment {

enum class Opcode {
    Mov,
    Lea,
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

Opcode classify_opcode(std::string_view mnemonic);

}  // namespace fragment
