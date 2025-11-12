#pragma once

#include <cstddef>
#include <string>

namespace splitter {

    struct PipelineConfig {
        std::string binary_path;
        std::string output_dir = "./partitions";
        std::size_t function_preview = 20;
        std::size_t loop_preview = 10;
        std::size_t sample_preview = 5;
        bool dump_full_disassembly = true;
        bool parallel_artifacts = false;
    };

}  // namespace splitter

