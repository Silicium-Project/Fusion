#pragma once

#include <string>
#include <vector>

#include "core/Function.hpp"
#include "core/MemorySegment.hpp"
#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"
#include "pipeline/PipelineConfig.hpp"

namespace splitter {

class PipelineContext {
public:
    explicit PipelineContext(PipelineConfig config);

    PipelineConfig config;
    std::vector<Function> functions;
    std::string disassembly;
    std::vector<Partition> partitions;
    std::vector<PartitionFiles> artifacts;
    std::vector<MemorySegment> memory_segments;
};

}  // namespace splitter
