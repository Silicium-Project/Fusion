#pragma once

#include <cstdint>
#include <vector>

namespace worker {

struct MemorySnapshot {
    uint64_t address = 0;
    std::vector<uint8_t> bytes;
};

}  // namespace worker

