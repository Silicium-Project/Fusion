#pragma once

#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"

namespace splitter {

class IArtifactBuilder {
public:
    virtual ~IArtifactBuilder() = default;
    virtual PartitionFiles CreatePartition(const Partition& partition) const = 0;
};

}  // namespace splitter
