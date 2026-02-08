#pragma once

#include "core/Common.hpp"

namespace fragment {

enum class AbiProfile {
    SystemV,
    WindowsX64
};

inline std::string abi_profile_name(AbiProfile profile) {
    switch (profile) {
        case AbiProfile::WindowsX64:
            return "windows-x64";
        case AbiProfile::SystemV:
        default:
            return "system-v";
    }
}

struct FdRule {
    int fd = -1;
    std::string input_data;   // non-empty means data fed to this fd
    bool capture = false;     // capture fragment writes on this fd
    std::string alias;        // optional label (stdout, stderr...)
};

struct ExecutorConfig {
    std::string binary_path;
    bool use_native_execution = false;
    AbiProfile abi_profile = AbiProfile::SystemV;
    std::vector<FdRule> fd_rules;  // full rules including 0/1/2
    std::size_t emulated_stack_size = 1 << 20;  // 1 MiB
};

#ifndef FRAGMENT_STACK_POINTER
#define FRAGMENT_STACK_POINTER "rsp"
#endif

}  // namespace fragment
