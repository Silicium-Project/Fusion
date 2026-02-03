#pragma once

#include <map>
#include <vector>

#include "core/Memory.hpp"

#include "worker/state/MemorySnapshot.hpp"

namespace worker {

class MemoryLut {
public:
    void clear();
    void apply_patch(const fragment::MemoryPatch& patch);
    std::vector<MemorySnapshot> snapshot() const;
    void seed(const std::vector<MemorySnapshot>& snapshots);
    const std::map<uint64_t, std::vector<uint8_t>>& chunks() const;

private:
    std::map<uint64_t, std::vector<uint8_t>> chunks_;
};

}  // namespace worker
