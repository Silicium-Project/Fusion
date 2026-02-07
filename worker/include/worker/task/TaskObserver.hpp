#pragma once

#include "worker/task/Task.hpp"
#include "worker/task/TaskReport.hpp"
#include "worker/core/TaskRouter.hpp"

namespace worker {

class TaskObserver {
public:
    virtual ~TaskObserver() = default;
    virtual void on_task_start(const TaskContext& context, const Task& task) = 0;
    virtual void on_task_finish(const TaskContext& context, const Task& task, const TaskReport& report) = 0;
};

}  // namespace worker
