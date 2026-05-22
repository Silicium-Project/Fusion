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
    explicit PartitionGraphBuilder(HashService hash_service = HashService());

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
                              const FlatMap<uint64_t, size_t>& addr_index,
                              const FlatMap<std::string, size_t>& id_index) const;
    void ComputeExternalInputs(std::vector<Partition>& partitions,
                               const FlatMap<std::string, size_t>& id_index) const;

    Normalizer normalizer_;
    HashService hash_service_;
};

using DefaultPartitionGraphBuilder = PartitionGraphBuilder<DefaultCallNormalizer>;

}  // namespace splitter

#include "partitioning/PartitionGraphBuilder.tpp"
