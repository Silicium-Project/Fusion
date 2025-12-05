#pragma once

#include <algorithm>
#include <iterator>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "core/Partition.hpp"
#include "partitioning/CallNormalizer.hpp"
#include "support/HashService.hpp"
#include "support/FlatMap.hpp"

namespace splitter {

using CallRef = std::pair<std::optional<uint64_t>, std::string>;
using CallMatrix = std::vector<std::vector<CallRef>>;

template <typename Normalizer = DefaultCallNormalizer>
class PartitionGraphBuilder {
public:
    explicit PartitionGraphBuilder(HashService hash_service = HashService())
        : hash_service_(std::move(hash_service)) {}

    void BuildGraph(std::vector<Partition>& partitions, const CallMatrix& call_refs) const;

private:
    void BuildIndices(const std::vector<Partition>& partitions,
                      FlatMap<uint64_t, size_t>& addr_index,
                      FlatMap<std::string, size_t>& id_index,
                      std::vector<std::set<std::string>>& parent_sets) const;
    void ResolveDependencies(std::vector<Partition>& partitions, const CallMatrix& call_refs,
                             const FlatMap<uint64_t, size_t>& addr_index,
                             std::vector<std::set<std::string>>& parent_sets) const;
    void AttachParents(std::vector<Partition>& partitions,
                       const std::vector<std::set<std::string>>& parent_sets) const;
    void CollectExternalCalls(std::vector<Partition>& partitions,
                              const CallMatrix& call_refs,
                              const FlatMap<uint64_t, size_t>& addr_index) const;
    void ComputeExternalInputs(std::vector<Partition>& partitions,
                               const FlatMap<std::string, size_t>& id_index) const;

    Normalizer normalizer_;
    HashService hash_service_;
};

using DefaultPartitionGraphBuilder = PartitionGraphBuilder<DefaultCallNormalizer>;

}  // namespace splitter

// Template definitions
namespace splitter {

namespace detail {
inline std::string UnresolvedLabel(const CallRef& call) {
    if (!call.second.empty())
        return call.second;
    if (!call.first.has_value())
        return "[indirect call]";
    std::ostringstream oss;
    oss << "0x" << std::hex << call.first.value();
    return oss.str();
}
}  // namespace detail

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::BuildIndices(const std::vector<Partition>& partitions,
                                                     FlatMap<uint64_t, size_t>& addr_index,
                                                     FlatMap<std::string, size_t>& id_index,
                                                     std::vector<std::set<std::string>>& parent_sets) const {
    parent_sets.clear();
    parent_sets.resize(partitions.size());
    addr_index.clear();
    id_index.clear();
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        for (const auto& func : partitions[idx].Functions())
            addr_index[func.StartAddr()] = idx;
        id_index[partitions[idx].Id()] = idx;
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::ResolveDependencies(
    std::vector<Partition>& partitions, const CallMatrix& call_refs,
    const FlatMap<uint64_t, size_t>& addr_index,
    std::vector<std::set<std::string>>& parent_sets) const {
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> dependency_set;
        std::set<std::string> unresolved_set;
        for (const auto& call : call_refs[idx]) {
            if (call.first.has_value()) {
                uint64_t target = call.first.value();
                auto it = addr_index.find(target);
                if (it != addr_index.end()) {
                    const std::string& child_id = partitions[it->second].Id();
                    if (child_id != partitions[idx].Id()) {
                        dependency_set.insert(child_id);
                        parent_sets[it->second].insert(partitions[idx].Id());
                    }
                } else {
                    unresolved_set.insert(detail::UnresolvedLabel(call));
                }
            } else {
                unresolved_set.insert(detail::UnresolvedLabel(call));
            }
        }
        partitions[idx].Dependencies().assign(dependency_set.begin(), dependency_set.end());
        partitions[idx].UnresolvedDependencies().assign(unresolved_set.begin(), unresolved_set.end());
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::AttachParents(
    std::vector<Partition>& partitions, const std::vector<std::set<std::string>>& parent_sets) const {
    for (size_t idx = 0; idx < partitions.size(); ++idx)
        partitions[idx].Parents().assign(parent_sets[idx].begin(), parent_sets[idx].end());
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::CollectExternalCalls(
    std::vector<Partition>& partitions, const CallMatrix& call_refs,
    const FlatMap<uint64_t, size_t>& addr_index) const {
    auto resolves_to_partition = [&](size_t idx, const CallRef& call) {
        if (!call.first.has_value())
            return false;
        auto it = addr_index.find(call.first.value());
        if (it == addr_index.end())
            return false;
        const auto& child_id = partitions[it->second].Id();
        return child_id != partitions[idx].Id();
    };

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        FlatStringSet names;
        bool needs_display = false;
        for (const auto& call : call_refs[idx]) {
            if (resolves_to_partition(idx, call))
                continue;
            auto symbol = normalizer_.Normalize(call);
            if (!symbol.empty()) {
                names.insert(symbol);
                if (!needs_display && normalizer_.IsGuiSymbol(symbol))
                    needs_display = true;
            }
        }
        partitions[idx].ExternalCalls() = std::move(names);
        partitions[idx].SetRequiresDisplay(needs_display);
        partitions[idx].SetBinHash(hash_service_.HashBytes(partitions[idx].RawBytes()));
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::ComputeExternalInputs(
    std::vector<Partition>& partitions, const FlatMap<std::string, size_t>& id_index) const {
    for (auto& partition : partitions) {
        FlatStringSet provided;
        for (const auto& parent_id : partition.Parents()) {
            auto it = id_index.find(parent_id);
            if (it == id_index.end())
                continue;
            const auto& outputs = partitions[it->second].Outputs();
            provided.insert(outputs.begin(), outputs.end());
        }
        FlatStringSet external;
        std::set_difference(partition.Inputs().begin(), partition.Inputs().end(),
                            provided.begin(), provided.end(),
                            std::inserter(external, external.begin()));
        partition.ExternalInputs() = external;
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::BuildGraph(std::vector<Partition>& partitions,
                                                   const CallMatrix& call_refs) const {
    FlatMap<uint64_t, size_t> addr_index;
    FlatMap<std::string, size_t> id_index;
    std::vector<std::set<std::string>> parent_sets;

    BuildIndices(partitions, addr_index, id_index, parent_sets);
    ResolveDependencies(partitions, call_refs, addr_index, parent_sets);
    AttachParents(partitions, parent_sets);
    CollectExternalCalls(partitions, call_refs, addr_index);
    ComputeExternalInputs(partitions, id_index);
}

}  // namespace splitter
