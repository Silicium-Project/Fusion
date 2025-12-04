#pragma once

#include <string>
#include <vector>

#include "splitter/core/Function.hpp"
#include "splitter/core/MemorySegment.hpp"
#include "splitter/core/Partition.hpp"
#include "splitter/core/PartitionFiles.hpp"
#include "splitter/pipeline/PipelineConfig.hpp"

namespace splitter {

class PipelineContext {
public:
    explicit PipelineContext(PipelineConfig config) : config(std::move(config)) {}

    PipelineConfig config;
    std::vector<Function> functions;
    std::string disassembly;
    std::vector<Partition> partitions;
    std::vector<PartitionFiles> artifacts;
    std::vector<MemorySegment> memory_segments;
};

}  // namespace splitter
