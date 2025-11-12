#pragma once

#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "splitter/artifacts.hpp"
#include "splitter/config.hpp"
#include "splitter/disassembly.hpp"
#include "splitter/partitioner.hpp"
#include "splitter/types.hpp"

namespace splitter {

    class PipelineRunner {
    public:
        PipelineRunner(PipelineConfig config,
                       std::unique_ptr<Disassembler> disassembler = nullptr,
                       std::unique_ptr<Partitioner> partitioner = nullptr,
                       std::unique_ptr<ArtifactBuilder> artifact_builder = nullptr);
        int run();

    private:
        void print_function_overview(const std::vector<Function>& functions) const;
        void dump_disassembly(const std::string& disasm) const;
        void report_loops(std::vector<Function>& functions) const;
        void report_partition(const BinaryPartition& partition) const;

        PipelineConfig config_;
        std::unique_ptr<Disassembler> disassembler_;
        std::unique_ptr<Partitioner> partitioner_;
        std::unique_ptr<ArtifactBuilder> artifact_builder_;
    };

    int run_cli(const std::vector<std::string_view>& args);

}  // namespace splitter
