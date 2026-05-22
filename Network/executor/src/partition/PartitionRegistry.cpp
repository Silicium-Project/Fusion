#include "partition/PartitionRegistry.hpp"

namespace fragment {

    void PartitionRegistry::reset() {
        partitions_.reset();
        lookup_.clear();
        preloaded_.clear();
    }

    void PartitionRegistry::set(const std::vector<PartitionInfo>* partitions) {
        reset();
        if (!partitions)
            return;
        partitions_ = std::cref(*partitions);
        for (const auto& p : *partitions)
            lookup_.emplace(p.id, std::cref(p));
    }

    std::optional<std::reference_wrapper<const std::vector<PartitionInfo>>> PartitionRegistry::partitions() const {
        return partitions_;
    }

    std::optional<std::reference_wrapper<const PartitionInfo>> PartitionRegistry::find(const std::string& id) const {
        auto it = lookup_.find(id);
        if (it == lookup_.end())
            return std::nullopt;
        return it->second;
    }

    bool PartitionRegistry::mark_preloaded(const std::string& id) {
        return preloaded_.insert(id).second;
    }

    PartitionRegistry& global_partition_registry() {
        static PartitionRegistry instance;
        return instance;
    }

}  // namespace fragment
