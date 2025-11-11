#pragma once

#include <string>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

    PartitionFiles create_standalone_partition(
        const BinaryPartition& partition, const std::string& output_dir);

    void write_summary(const std::vector<BinaryPartition>& partitions,
                        const std::vector<PartitionFiles>& artifacts,
                        const std::string& output_dir,
                        const std::string& binary_path);

}  // namespace splitter
