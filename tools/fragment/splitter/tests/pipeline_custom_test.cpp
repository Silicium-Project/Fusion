#include <gtest/gtest.h>

#include <memory>
#include <string>
#include <vector>

#include "splitter/pipeline/PipelineFactory.hpp"
#include "splitter/pipeline/IPipelinePhase.hpp"
#include "splitter/pipeline/Paths.hpp"

using namespace splitter;

namespace {

class FakePhase : public IPipelinePhase {
public:
    FakePhase(std::string name, std::shared_ptr<std::vector<std::string>> log)
        : name_(std::move(name)), log_(std::move(log)) {}

    const char* Name() const override { return name_.c_str(); }

    void Execute(PipelineContext&) override {
        if (log_)
            log_->push_back(name_);
    }

private:
    std::string name_;
    std::shared_ptr<std::vector<std::string>> log_;
};

}  // namespace

TEST(PipelineFactory, BuildCustomRunsAllPhases) {
    PipelineConfig config;
    config.binary_path = BinaryPath("dummy.bin");

    auto log = std::make_shared<std::vector<std::string>>();

    auto runner = PipelineFactory::BuildCustom(
        config,
        [log](const PipelineConfig&) {
            return std::make_unique<FakePhase>("disasm", log);
        },
        [log](const PipelineConfig&) {
            return std::make_unique<FakePhase>("analysis", log);
        },
        [log](const PipelineConfig&) {
            return std::make_unique<FakePhase>("partitioning", log);
        },
        [log](const PipelineConfig&) {
            return std::make_unique<FakePhase>("artifacts", log);
        });

    int rc = runner->Run();
    ASSERT_EQ(rc, 0);
    ASSERT_EQ(log->size(), 4u);
    EXPECT_EQ((*log)[0], "disasm");
    EXPECT_EQ((*log)[1], "analysis");
    EXPECT_EQ((*log)[2], "partitioning");
    EXPECT_EQ((*log)[3], "artifacts");
}
