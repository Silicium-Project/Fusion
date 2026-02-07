#pragma once

#include <memory>

namespace worker {

class TaskRouter;
class Worker;

class TaskHandlerFactory {
public:
    virtual ~TaskHandlerFactory() = default;
    virtual void register_handlers(TaskRouter& router, Worker& worker) const = 0;
};

std::unique_ptr<TaskHandlerFactory> make_task_handler_factory();

}  // namespace worker
