#pragma once

#include <string>
#include <vector>

#include "core/LibraryInfo.hpp"
#include "core/MemorySegment.hpp"
#include "core/Partition.hpp"

namespace splitter {

class PartitionSummary {
public:
    std::string binary_path;
    std::string binary_hash;
    bool can_split = true;
    std::string memory_hash;
    std::string summary_hash;
    std::vector<std::string> required_libraries;
    std::vector<LibraryInfo> libraries;
    std::vector<Partition> partitions;
    std::vector<MemorySegment> initial_memory;
};

}  // namespace splitter
