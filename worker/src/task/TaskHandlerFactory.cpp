#include "worker/task/TaskHandlerFactory.hpp"

#include <utility>

#include "worker/core/TaskRouter.hpp"
#include "worker/core/Worker.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker {

class DefaultTaskHandlerFactory : public TaskHandlerFactory {
public:
    void register_handlers(TaskRouter& router, Worker& worker) const override {
        router.register_handler(
            TaskType::Binary,
            std::make_unique<FunctionTaskHandler>(
                [&worker](const TaskContext& context, const Task& task) {
                    return worker.run_binary_task(context, task);
                })
        );
        router.register_handler(
            TaskType::Health,
            std::make_unique<FunctionTaskHandler>(
                [&worker](const TaskContext& context, const Task& task) {
                    return worker.run_health_task(context, task);
                })
        );
    }
};

std::unique_ptr<TaskHandlerFactory> make_task_handler_factory() {
    return std::make_unique<DefaultTaskHandlerFactory>();
}

}  // namespace worker
