#pragma once

#include <filesystem>
#include <vector>

#include "core/MemorySegment.hpp"
#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"

namespace splitter {

class ISummaryWriter {
public:
    virtual ~ISummaryWriter() = default;
    virtual void Write(const std::vector<Partition>& partitions,
                       const std::vector<PartitionFiles>& artifacts,
                       const std::vector<MemorySegment>& memory_segments,
                       const std::filesystem::path& binary_path) const = 0;
};

}  // namespace splitter
