#pragma once

#include "core/Common.hpp"

namespace fragment {

struct FdRule {
    int fd = -1;
    std::string input_data;   // si non vide, fourni au fd (lecture côté fragment)
    bool capture = false;     // capture les écritures du fragment sur ce fd
    std::string alias;        // étiquette facultative (stdout, stderr, etc.)
};

struct ExecutorConfig {
    std::string binary_path;
    bool use_native_execution = false;
    std::vector<FdRule> fd_rules;  // règles complètes, y compris 0/1/2
    std::size_t emulated_stack_size = 1 << 20;  // 1 MiB
};

#ifndef FRAGMENT_STACK_POINTER
#define FRAGMENT_STACK_POINTER "rsp"
#endif

}  // namespace fragment
