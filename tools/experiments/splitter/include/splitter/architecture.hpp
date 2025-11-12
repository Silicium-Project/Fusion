#pragma once

#include <string_view>

#include "splitter/register_catalog.hpp"

#ifndef SPLITTER_ASM_MEMORY_KEYWORD
#define SPLITTER_ASM_MEMORY_KEYWORD "PTR"
#endif

#ifndef SPLITTER_ASM_STACK_POINTER_REG
#define SPLITTER_ASM_STACK_POINTER_REG "rsp"
#endif

namespace splitter {

    class ArchitectureProfile {
    public:
        static const ArchitectureProfile& instance();

        [[nodiscard]] std::string_view memory_keyword() const noexcept {
            return memory_keyword_;
        }

        [[nodiscard]] std::string_view stack_pointer() const noexcept {
            return stack_pointer_;
        }

        [[nodiscard]] const RegisterCatalog& registers() const noexcept {
            return RegisterCatalog::instance();
        }

    private:
        ArchitectureProfile();

        std::string_view memory_keyword_;
        std::string_view stack_pointer_;
    };

    inline const ArchitectureProfile& ArchitectureProfile::instance() {
        static const ArchitectureProfile profile;
        return profile;
    }

    inline ArchitectureProfile::ArchitectureProfile()
    : memory_keyword_(SPLITTER_ASM_MEMORY_KEYWORD)
    , stack_pointer_(SPLITTER_ASM_STACK_POINTER_REG) {}

}  // namespace splitter

