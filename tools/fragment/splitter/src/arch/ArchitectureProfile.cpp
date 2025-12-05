#include "arch/ArchitectureProfile.hpp"

namespace splitter {

const ArchitectureProfile& ArchitectureProfile::Instance() {
    static const ArchitectureProfile profile;
    return profile;
}

ArchitectureProfile::ArchitectureProfile()
    : memory_keyword_(SPLITTER_ASM_MEMORY_KEYWORD),
      stack_pointer_(SPLITTER_ASM_STACK_POINTER_REG) {}

}  // namespace splitter
