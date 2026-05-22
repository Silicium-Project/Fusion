#include <gtest/gtest.h>

#include "worker/core/Worker.hpp"

namespace worker {

TEST(HealthTask, ReturnsTelemetryPayload) {
    WorkerConfig config;
    config.mode = ExecutionMode::Emulator;
    config.reset_between_tasks = true;
    Worker worker(config);

    fragment::PartitionInfo partition;
    partition.id = "health";

    Task task;
    task.type = TaskType::Health;
    task.partition_id = "health";

    TaskReport report = worker.run_task(partition, "", "", "", task);

    EXPECT_TRUE(report.result.success);
    EXPECT_EQ(report.telemetry.type, TaskType::Health);
    EXPECT_EQ(report.telemetry.status, "success");
    EXPECT_NE(std::string::npos, report.result.program_stdout.find("\"status\":\"ok\""));
    EXPECT_NE(std::string::npos, report.result.program_stdout.find("\"mode\":\"emu\""));
}

}  // namespace worker
