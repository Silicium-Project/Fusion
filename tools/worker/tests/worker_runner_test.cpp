#include <gtest/gtest.h>

#include "worker/job_runner.hpp"

TEST(WorkerRunner, ExecutesPartitionFromSummary) {
    const std::string summary = "../experiments/splitter/partitions/summary.json";

    worker::WorkerConfig config;
    worker::JobRunner runner(summary, config);

    worker::Task task;
    task.partition_id = "func_3_main";
    task.inputs["rax"] = 0;

    auto report = runner.execute(task);
    EXPECT_EQ(report.partition_id, "func_3_main");
    EXPECT_TRUE(report.result.success);
    EXPECT_GT(report.result.instructions_executed, 0u);
}
