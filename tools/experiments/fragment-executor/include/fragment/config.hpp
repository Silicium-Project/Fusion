#pragma once

#include "fragment/common.hpp"

namespace fragment {

struct ExecutorConfig {
    std::string binary_path;
    bool use_native_execution = false;
    bool capture_stdout = true;
    std::size_t emulated_stack_size = 1 << 20;  // 1 MiB
};

#ifndef FRAGMENT_STACK_POINTER
#define FRAGMENT_STACK_POINTER "rsp"
#endif

}  // namespace fragment
