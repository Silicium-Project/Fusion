#pragma once

#include <memory>
#include <string_view>
#include <vector>

#include "splitter/pipeline/IPipelinePhase.hpp"
#include "splitter/pipeline/PipelineContext.hpp"
#include "splitter/pipeline/IReporter.hpp"

namespace splitter {

class PipelineRunner {
public:
    PipelineRunner(PipelineConfig config,
                   std::unique_ptr<IPipelinePhase> disassembly,
                   std::unique_ptr<IPipelinePhase> analysis,
                   std::unique_ptr<IPipelinePhase> partitioning,
                   std::unique_ptr<IPipelinePhase> artifacts,
                   std::unique_ptr<IReporter> reporter = nullptr);

    int Run();

private:
    void PrintFunctionOverview(const std::vector<Function>& functions) const;
    void DumpDisassembly(const std::string& disasm) const;
    void ReportLoops(std::vector<Function>& functions) const;
    void ReportPartition(const Partition& partition) const;

    PipelineContext context_;
    std::unique_ptr<IPipelinePhase> disassembly_;
    std::unique_ptr<IPipelinePhase> analysis_;
    std::unique_ptr<IPipelinePhase> partitioning_;
    std::unique_ptr<IPipelinePhase> artifacts_;
    std::unique_ptr<IReporter> reporter_;
};

int RunCli(const std::vector<std::string_view>& args);

}  // namespace splitter
