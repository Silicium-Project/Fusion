#include <filesystem>
#include <functional>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "pipeline/PipelineRunner.hpp"
#include "pipeline/IPipelinePhase.hpp"
#include "pipeline/PipelineConfig.hpp"
#include "core/Function.hpp"
#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"

namespace fs = std::filesystem;
using namespace splitter;

namespace {

class RecordingPhase : public IPipelinePhase {
public:
    RecordingPhase(std::string name,
                   std::vector<std::string>* log,
                   std::function<void(PipelineContext&)> fn)
        : name_(std::move(name)), log_(log), fn_(std::move(fn)) {}

    std::string Name() const override { return name_; }

    void Execute(PipelineContext& context) override {
        if (log_)
            log_->push_back(name_);
        if (fn_)
            fn_(context);
    }

private:
    std::string name_;
    std::vector<std::string>* log_;
    std::function<void(PipelineContext&)> fn_;
};

Function MakeFunction(std::string name, uint64_t start, uint64_t end) {
    Function f;
    f.SetName(std::move(name));
    f.SetStartAddr(start);
    f.SetEndAddr(end);
    return f;
}

}  // namespace

TEST(PipelineIntegration, RunsPipelineWithStubs) {
    fs::path tmp = fs::temp_directory_path() / "splitter_integration_test";
    fs::remove_all(tmp);

    PipelineConfig config;
    config.binary_path = BinaryPath("fake.bin");
    config.output_dir = OutputDir(tmp.string());
    config.dump_full_disassembly = false;

    std::vector<std::string> executed;

    auto disassembly = std::make_unique<RecordingPhase>(
        "Disassembly", &executed, [](PipelineContext& ctx) {
            ctx.disassembly = "int main() {}";
            ctx.functions.push_back(MakeFunction("main", 0x10, 0x30));
        });

    auto analysis = std::make_unique<RecordingPhase>(
        "Analysis", &executed, [](PipelineContext& ctx) {
            if (!ctx.functions.empty())
                ctx.functions.front().SetIsLoop(true);
        });

    auto partitioning = std::make_unique<RecordingPhase>(
        "Partitioning", &executed, [](PipelineContext& ctx) {
            Partition p;
            p.SetId("P1");
            p.SetStartAddr(0x10);
            p.SetEndAddr(0x30);
            p.Functions() = ctx.functions;
            p.RawBytes().push_back(0x90);
            p.Inputs().insert(std::string("input"));
            p.Outputs().insert(std::string("output"));
            ctx.partitions = {p};
        });

    auto artifacts = std::make_unique<RecordingPhase>(
        "Artifacts", &executed, [](PipelineContext& ctx) {
            PartitionFiles files;
            files.SetAsmFile("p1.asm");
            files.SetBinFile("p1.bin");
            files.SetWrapperFile("p1_wrap.c");
            ctx.artifacts = {files};
        });

    PipelineRunner runner(std::move(config), std::move(disassembly), std::move(analysis),
                          std::move(partitioning), std::move(artifacts), nullptr);

    EXPECT_EQ(runner.Run(), 0);
    const std::vector<std::string> expected = {"Disassembly", "Analysis", "Partitioning", "Artifacts"};
    EXPECT_EQ(executed, expected);

    fs::remove_all(tmp);
}
