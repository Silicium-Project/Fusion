#pragma once

#include <functional>
#include <memory>
#include <string_view>
#include <vector>

#include "pipeline/IPipelinePhase.hpp"
#include "pipeline/PipelineContext.hpp"
#include "pipeline/PipelineError.hpp"
#include "pipeline/IReporter.hpp"

namespace splitter {

class PipelineRunner {
public:
    struct PipelineStep {
        std::string key;
        PipelineExit on_error = PipelineExit::UnknownError;
        std::unique_ptr<IPipelinePhase> phase;
    };

    PipelineRunner(PipelineConfig config,
                   std::vector<PipelineStep> steps,
                   std::shared_ptr<IReporter> reporter = {});
    PipelineRunner(PipelineConfig config,
                   std::unique_ptr<IPipelinePhase> disassembly,
                   std::unique_ptr<IPipelinePhase> analysis,
                   std::unique_ptr<IPipelinePhase> partitioning,
                   std::unique_ptr<IPipelinePhase> artifacts,
                   std::shared_ptr<IReporter> reporter = {});

    int Run();

private:
    void PrintFunctionOverview(const std::vector<Function>& functions) const;
    void DumpDisassembly(const std::string& disasm) const;
    void ReportLoops(std::vector<Function>& functions) const;
    void ReportPartition(const Partition& partition) const;

    PipelineContext context_;
    std::vector<PipelineStep> steps_;
    std::shared_ptr<IReporter> reporter_;
};

int RunCli(const std::vector<std::string_view>& args);

}  // namespace splitter
