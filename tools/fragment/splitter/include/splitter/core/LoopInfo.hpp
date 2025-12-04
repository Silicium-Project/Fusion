#pragma once

#include <cstdint>

namespace splitter {

struct LoopInfo {
    uint64_t source_addr = 0;
    uint64_t target_addr = 0;
    bool backward = false;
};

}  // namespace splitter
