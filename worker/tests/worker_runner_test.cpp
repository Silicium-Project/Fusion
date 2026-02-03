#include <gtest/gtest.h>

#include "worker/runtime/JobRunner.hpp"

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
