#pragma once

#include "partition/PartitionSummary.hpp"

#include <optional>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace fragment {

class PartitionRegistry {
public:
    void set(const std::vector<PartitionInfo>* partitions);
    void reset();

    std::optional<std::reference_wrapper<const std::vector<PartitionInfo>>> partitions() const;
    std::optional<std::reference_wrapper<const PartitionInfo>> find(const std::string& id) const;
    bool mark_preloaded(const std::string& id);

private:
    std::optional<std::reference_wrapper<const std::vector<PartitionInfo>>> partitions_;
    std::unordered_map<std::string, std::reference_wrapper<const PartitionInfo>> lookup_;
    std::unordered_set<std::string> preloaded_;
};

// Singleton simple pour partager le registre.
PartitionRegistry& global_partition_registry();

}  // namespace fragment
