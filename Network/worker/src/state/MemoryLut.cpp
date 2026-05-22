#include "worker/state/MemoryLut.hpp"

namespace worker {

void MemoryLut::clear() {
    chunks_.clear();
}

void MemoryLut::apply_patch(const fragment::MemoryPatch& patch) {
    if (patch.after.empty())
        return;
    chunks_[patch.address] = patch.after;
}

std::vector<MemorySnapshot> MemoryLut::snapshot() const {
    std::vector<MemorySnapshot> snapshots;
    snapshots.reserve(chunks_.size());
    for (const auto& [address, bytes] : chunks_) {
        MemorySnapshot snapshot;
        snapshot.address = address;
        snapshot.bytes = bytes;
        snapshots.push_back(std::move(snapshot));
    }
    return snapshots;
}

void MemoryLut::seed(const std::vector<MemorySnapshot>& snapshots) {
    for (const auto& snapshot : snapshots)
        chunks_[snapshot.address] = snapshot.bytes;
}

const std::map<uint64_t, std::vector<uint8_t>>& MemoryLut::chunks() const {
    return chunks_;
}

}  // namespace worker
