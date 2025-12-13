#pragma once

#include <string_view>

#include "arch/RegisterCatalog.hpp"

#ifndef SPLITTER_ASM_MEMORY_KEYWORD
#define SPLITTER_ASM_MEMORY_KEYWORD "PTR"
#endif

#ifndef SPLITTER_ASM_STACK_POINTER_REG
#define SPLITTER_ASM_STACK_POINTER_REG "rsp"
#endif

namespace splitter {

class ArchitectureProfile {
public:
    static const ArchitectureProfile& Instance();

    [[nodiscard]] std::string_view MemoryKeyword() const noexcept;
    [[nodiscard]] std::string_view StackPointer() const noexcept;
    [[nodiscard]] const RegisterCatalog& Registers() const noexcept;

private:
    ArchitectureProfile();

    std::string_view memory_keyword_;
    std::string_view stack_pointer_;
};

}  // namespace splitter
