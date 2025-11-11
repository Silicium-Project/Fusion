#pragma once

#include <set>
#include <string>
#include <vector>

namespace fragment {

struct PartitionInfo {
    std::string id;
    std::string asm_path;
    std::string bin_path;
    std::string wrapper_path;
    std::set<std::string> inputs;
    std::set<std::string> external_inputs;
    std::set<std::string> outputs;
    std::vector<std::string> parents;
    std::vector<std::string> dependencies;
    std::vector<std::string> unresolved_calls;
    bool parallelizable = false;
};

struct PartitionSummary {
    std::string binary_path;
    std::vector<PartitionInfo> partitions;
};

PartitionSummary load_partition_summary(const std::string& summary_path);
std::vector<std::string> order_partitions(const PartitionSummary& summary);
std::vector<std::string> order_partitions(const std::vector<PartitionInfo>& partitions);

}  // namespace fragment
