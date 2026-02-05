#pragma once

#include <cstddef>
#include <string>

#include "pipeline/BinaryPath.hpp"
#include "pipeline/OutputDir.hpp"

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
    std::string hash_algo;      // "fnv", "std" ou vide pour auto/env
    std::string resolver;       // "ldd", "readelf" ou vide pour auto/env
    std::string symbol_indexer; // "nm", "objdump" ou vide pour auto/env
    std::string disassembler;   // "objdump" ou vide pour auto/env
    std::string reporter = "console";  // "console", "json", "ndjson"
    std::string report_file;           // optionnel: chemin de log des reports
};

}  // namespace splitter
