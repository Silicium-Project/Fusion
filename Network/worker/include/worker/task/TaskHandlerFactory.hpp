#pragma once

#include <memory>

namespace worker {

class TaskRouter;
class Worker;

class ITaskHandlerFactory {
public:
    virtual ~ITaskHandlerFactory() = default;
    virtual void register_handlers(TaskRouter& router, Worker& worker) const = 0;
};

std::unique_ptr<ITaskHandlerFactory> make_task_handler_factory();

}  // namespace worker
