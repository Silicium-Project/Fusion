#pragma once

#include <cstddef>

#include "splitter/pipeline/Paths.hpp"

namespace splitter {

class PipelineConfig {
public:
    BinaryPath binary_path;
    OutputDir output_dir = OutputDir("./partitions");
    std::size_t function_preview = 20;
    std::size_t loop_preview = 10;
    std::size_t sample_preview = 5;
    bool dump_full_disassembly = true;
    bool parallel_artifacts = false;
};

}  // namespace splitter
