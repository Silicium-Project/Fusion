#include <gtest/gtest.h>

#include "worker/core/TaskRouter.hpp"

namespace worker {

namespace {

class DummyHandler : public TaskHandler {
public:
    explicit DummyHandler(bool& called)
    : called_(called) {}

    TaskReport handle(const TaskContext& context, const Task& task) override {
        called_ = true;
        TaskReport report;
        report.partition_id = context.partition.id;
        report.telemetry.task_id = task.partition_id;
        report.result.success = true;
        return report;
    }

private:
    bool& called_;
};

}  // namespace

TEST(TaskRouter, DispatchesByType) {
    TaskRouter router;
    bool called = false;
    router.register_handler(TaskType::Binary, std::make_unique<DummyHandler>(called));

    fragment::PartitionInfo partition;
    partition.id = "p1";
    TaskContext context{partition, "/tmp/a.asm", "/tmp/bin", "/tmp/summary.json"};
    Task task;
    task.type = TaskType::Binary;
    task.partition_id = "p1";

    TaskReport report = router.execute(context, task);
    EXPECT_TRUE(called);
    EXPECT_EQ(report.partition_id, "p1");
    EXPECT_EQ(report.telemetry.task_id, "p1");
    EXPECT_TRUE(report.result.success);
}

TEST(TaskRouter, UnknownTypeThrows) {
    TaskRouter router;

    fragment::PartitionInfo partition;
    partition.id = "p2";
    TaskContext context{partition, "", "", ""};
    Task task;
    task.partition_id = "p2";
    task.type = static_cast<TaskType>(999);

    EXPECT_THROW(router.execute(context, task), std::runtime_error);
}

}  // namespace worker
