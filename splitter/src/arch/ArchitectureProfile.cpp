#include "arch/ArchitectureProfile.hpp"

namespace splitter {

const ArchitectureProfile& ArchitectureProfile::Instance() {
    static const ArchitectureProfile profile;
    return profile;
}

ArchitectureProfile::ArchitectureProfile()
    : memory_keyword_(SPLITTER_ASM_MEMORY_KEYWORD),
      stack_pointer_(SPLITTER_ASM_STACK_POINTER_REG) {}

std::string_view ArchitectureProfile::MemoryKeyword() const noexcept {
    return memory_keyword_;
}

std::string_view ArchitectureProfile::StackPointer() const noexcept {
    return stack_pointer_;
}

const RegisterCatalog& ArchitectureProfile::Registers() const noexcept {
    return RegisterCatalog::Instance();
}

}  // namespace splitter
