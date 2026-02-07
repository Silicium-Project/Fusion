#include "worker/core/TaskRouter.hpp"

namespace worker {

void TaskRouter::register_handler(TaskType type, std::unique_ptr<TaskHandler> handler) {
    if (!handler)
        throw std::runtime_error("Handler de tâche nul");
    handlers_[type] = std::move(handler);
}

TaskReport TaskRouter::execute(const TaskContext& context, const Task& task) const {
    const auto it = handlers_.find(task.type);
    if (it == handlers_.end())
        throw std::runtime_error("Aucun handler pour le type: " + task_type_to_string(task.type));
    return it->second->handle(context, task);
}

}  // namespace worker
