#include <gtest/gtest.h>

#include "worker/runtime/JobRunner.hpp"
#include "worker/task/TaskObserver.hpp"

namespace {

class CountingObserver : public worker::TaskObserver {
public:
    void on_task_start(const worker::TaskContext&, const worker::Task&) override {
        ++starts;
    }

    void on_task_finish(const worker::TaskContext&,
                        const worker::Task&,
                        const worker::TaskReport&) override {
        ++finishes;
    }

    int starts = 0;
    int finishes = 0;
};

}  // namespace

TEST(WorkerRunner, ExecutesPartitionFromSummary) {
    const std::string summary = "../demo/worker/summary.json";

    worker::WorkerConfig config;
    config.mode = worker::ExecutionMode::Emulator;
    worker::JobRunner runner(summary, config);

    worker::Task task;
    task.partition_id = "writer";
    task.inputs["rax"] = 0;

    auto report = runner.execute(task);
    EXPECT_EQ(report.partition_id, "writer");
    EXPECT_TRUE(report.result.success);
    EXPECT_GT(report.result.instructions_executed, 0u);
}

TEST(WorkerRunner, ObserverReceivesHealthTaskEvents) {
    const std::string summary = "../demo/worker/summary.json";

    worker::WorkerConfig config;
    config.mode = worker::ExecutionMode::Emulator;
    worker::JobRunner runner(summary, config);

    auto observer = std::make_shared<CountingObserver>();
    runner.add_observer(observer);

    worker::Task health;
    health.type = worker::TaskType::Health;
    health.partition_id = "health-1";

    auto report = runner.execute(health);
    EXPECT_TRUE(report.result.success);
    EXPECT_EQ(1, observer->starts);
    EXPECT_EQ(1, observer->finishes);
}

TEST(WorkerRunner, RunnerModeCanBeUpdatedAtRuntime) {
    const std::string summary = "../demo/worker/summary.json";

    worker::WorkerConfig config;
    config.mode = worker::ExecutionMode::Emulator;
    worker::JobRunner runner(summary, config);

    EXPECT_EQ(worker::ExecutionMode::Emulator, runner.mode());
    runner.set_mode(worker::ExecutionMode::Native);
    EXPECT_EQ(worker::ExecutionMode::Native, runner.mode());
}
