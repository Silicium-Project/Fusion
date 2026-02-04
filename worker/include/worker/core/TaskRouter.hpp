#pragma once

#include <map>
#include <memory>
#include <string>
#include <stdexcept>

#include "partition/PartitionSummary.hpp"

#include "worker/task/Task.hpp"
#include "worker/task/TaskReport.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker {

struct TaskContext {
    const fragment::PartitionInfo& partition;
    std::string asm_path;
    std::string binary_path;
    std::string summary_path;
};

class TaskHandler {
public:
    virtual ~TaskHandler() = default;
    virtual TaskReport handle(const TaskContext& context, const Task& task) = 0;
};

class TaskRouter {
public:
    void register_handler(TaskType type, std::unique_ptr<TaskHandler> handler);
    TaskReport execute(const TaskContext& context, const Task& task) const;

private:
    std::map<TaskType, std::unique_ptr<TaskHandler>> handlers_;
};

}  // namespace worker
