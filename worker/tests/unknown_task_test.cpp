#include <gtest/gtest.h>

#include "worker/core/Worker.hpp"

namespace worker {

TEST(WorkerUnknownTask, ReturnsFailureWithoutThrow) {
    WorkerConfig config;
    Worker worker(config);

    fragment::PartitionInfo partition;
    partition.id = "p1";

    Task task;
    task.partition_id = "p1";
    task.type = static_cast<TaskType>(999);

    TaskReport report;
    EXPECT_NO_THROW({
        report = worker.run_task(partition, "", "", "", task);
    });

    EXPECT_FALSE(report.result.success);
    EXPECT_FALSE(report.result.error_message.empty());
}

}  // namespace worker
