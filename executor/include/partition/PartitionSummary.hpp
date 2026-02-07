#pragma once

#include "core/Common.hpp"

namespace fragment {

inline constexpr uint32_t kPartitionSummarySchemaVersion = 1;

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
    std::string os;
    std::string format;
    std::string bin_hash;
    std::string partition_hash;
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
    uint32_t schema_version = kPartitionSummarySchemaVersion;
    std::string binary_path;
    std::string binary_os;
    std::string binary_format;
    std::string binary_hash;
    std::string hash_algo;
    bool can_split = true;
    std::string memory_hash;
    std::string summary_hash;
    std::vector<std::string> required_libraries;
    std::vector<LibraryInfo> libraries;
    std::vector<PartitionInfo> partitions;
    std::vector<MemoryRegion> initial_memory;
};

PartitionSummary load_partition_summary(const std::string& summary_path, bool skip_memory_check = false);

std::vector<std::string> order_partitions(const PartitionSummary& summary);

std::vector<std::string> order_partitions(const std::vector<PartitionInfo>& partitions);

void set_partition_registry(const std::vector<PartitionInfo>* partitions);

}  // namespace fragment
