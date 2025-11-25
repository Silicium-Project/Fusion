#pragma once

#include "fragment/common.hpp"

namespace fragment {

struct PartitionDependency {
    std::string id;
    std::string asm_path;
    std::string bin_path;
    std::optional<uint64_t> start_address;
    size_t binary_size = 0;
};

struct PartitionInfo {
    std::string id;
    std::string asm_path;
    std::string bin_path;
    std::string wrapper_path;
    std::string bin_hash;
    std::optional<uint64_t> start_address;
    std::optional<uint64_t> end_address;
    size_t binary_size = 0;
    std::set<std::string> inputs;
    std::set<std::string> external_inputs;
    std::set<std::string> outputs;
    std::set<std::string> external_calls;
    std::set<std::string> required_libraries;
    bool requires_display = false;
    std::vector<std::string> parents;
    std::vector<std::string> dependencies;
    std::vector<std::string> unresolved_calls;
    std::vector<PartitionDependency> resolved_dependencies;
    bool parallelizable = false;
};

struct MemoryRegion {
    std::string name;
    uint64_t address = 0;
    std::vector<uint8_t> bytes;
};

struct LibraryInfo {
    std::string name;
    std::string path;
    std::string soname;
    std::string build_id;
};

struct PartitionSummary {
    std::string binary_path;
    std::string binary_hash;
    bool can_split = true;
    std::vector<std::string> required_libraries;
    std::vector<LibraryInfo> libraries;
    std::vector<PartitionInfo> partitions;
    std::vector<MemoryRegion> initial_memory;
};

PartitionSummary load_partition_summary(const std::string& summary_path);

std::vector<std::string> order_partitions(const PartitionSummary& summary);

std::vector<std::string> order_partitions(const std::vector<PartitionInfo>& partitions);

void set_partition_registry(const std::vector<PartitionInfo>* partitions);

}  // namespace fragment
