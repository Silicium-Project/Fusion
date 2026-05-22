#include <filesystem>
#include <functional>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "pipeline/PipelineRunner.hpp"
#include "pipeline/IPipelinePhase.hpp"
#include "pipeline/JsonReporter.hpp"
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

std::size_t CountOccurrences(const std::string& text, const std::string& needle) {
    if (needle.empty())
        return 0;
    std::size_t count = 0;
    std::size_t pos = 0;
    while ((pos = text.find(needle, pos)) != std::string::npos) {
        ++count;
        pos += needle.size();
    }
    return count;
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

TEST(PipelineIntegration, EmitsStructuredLifecycleEvents) {
    fs::path tmp = fs::temp_directory_path() / "splitter_integration_structured_logs";
    fs::remove_all(tmp);

    PipelineConfig config;
    config.binary_path = BinaryPath("fake.bin");
    config.output_dir = OutputDir(tmp.string());
    config.dump_full_disassembly = false;

    auto disassembly = std::make_unique<RecordingPhase>(
        "Disassembly", nullptr, [](PipelineContext& ctx) {
            ctx.disassembly = "int main() {}";
            ctx.functions.push_back(MakeFunction("main", 0x10, 0x30));
        });
    auto analysis = std::make_unique<RecordingPhase>("Analysis", nullptr, nullptr);
    auto partitioning = std::make_unique<RecordingPhase>(
        "Partitioning", nullptr, [](PipelineContext& ctx) {
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
    auto artifacts = std::make_unique<RecordingPhase>("Artifacts", nullptr, nullptr);

    auto out = std::make_shared<std::ostringstream>();
    auto reporter = std::make_shared<JsonReporter>(out, JsonReporter::Mode::StructuredV1Ndjson);

    PipelineRunner runner(std::move(config), std::move(disassembly), std::move(analysis),
                          std::move(partitioning), std::move(artifacts), reporter);

    EXPECT_EQ(runner.Run(), 0);

    const std::string logs = out->str();
    EXPECT_NE(logs.find("\"event\":\"run_started\""), std::string::npos);
    EXPECT_EQ(CountOccurrences(logs, "\"event\":\"phase_started\""), 4u);
    EXPECT_EQ(CountOccurrences(logs, "\"event\":\"phase_completed\""), 4u);
    EXPECT_NE(logs.find("\"event\":\"run_completed\""), std::string::npos);
    EXPECT_NE(logs.find("\"event\":\"functions_reported\""), std::string::npos);
    EXPECT_NE(logs.find("\"event\":\"partition_reported\""), std::string::npos);

    fs::remove_all(tmp);
}

TEST(PipelineIntegration, EmitsStructuredPhaseFailedEventOnError) {
    fs::path tmp = fs::temp_directory_path() / "splitter_integration_structured_logs_error";
    fs::remove_all(tmp);

    PipelineConfig config;
    config.binary_path = BinaryPath("fake.bin");
    config.output_dir = OutputDir(tmp.string());
    config.dump_full_disassembly = false;

    auto disassembly = std::make_unique<RecordingPhase>(
        "Disassembly", nullptr, [](PipelineContext& ctx) {
            ctx.functions.push_back(MakeFunction("main", 0x10, 0x30));
        });
    auto analysis = std::make_unique<RecordingPhase>(
        "Analysis", nullptr, [](PipelineContext&) { throw std::runtime_error("analysis boom"); });
    auto partitioning = std::make_unique<RecordingPhase>("Partitioning", nullptr, nullptr);
    auto artifacts = std::make_unique<RecordingPhase>("Artifacts", nullptr, nullptr);

    auto out = std::make_shared<std::ostringstream>();
    auto reporter = std::make_shared<JsonReporter>(out, JsonReporter::Mode::StructuredV1Ndjson);

    PipelineRunner runner(std::move(config), std::move(disassembly), std::move(analysis),
                          std::move(partitioning), std::move(artifacts), reporter);

    EXPECT_NE(runner.Run(), 0);

    const std::string logs = out->str();
    EXPECT_NE(logs.find("\"event\":\"phase_failed\""), std::string::npos);
    EXPECT_NE(logs.find("\"phase\":\"analysis\""), std::string::npos);
    EXPECT_NE(logs.find("\"error\":\"analysis boom\""), std::string::npos);
    EXPECT_NE(logs.find("\"event\":\"run_completed\""), std::string::npos);

    fs::remove_all(tmp);
}
