#pragma once

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "partition/PartitionSummary.hpp"

#include "worker/backend/BackendConnector.hpp"
#include "worker/backend/BackendConnectorFactory.hpp"
#include "worker/state/MemoryLut.hpp"
#include "worker/task/Task.hpp"
#include "worker/task/TaskReport.hpp"
#include "worker/task/TaskTypes.hpp"
#include "worker/task/TaskHandlerFactory.hpp"
#include "worker/task/TaskObserver.hpp"
#include "worker/core/TaskRouter.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class DefaultTaskHandlerFactory;

struct WorkerDependencies {
    std::unique_ptr<BackendConnector> connector{};
    std::unique_ptr<BackendConnectorFactory> connector_factory{};
    std::unique_ptr<TaskHandlerFactory> handler_factory{};
    std::vector<std::shared_ptr<TaskObserver>> observers{};
};

class Worker {
public:
    explicit Worker(WorkerConfig config = {});
    Worker(WorkerConfig config, std::unique_ptr<BackendConnector> connector);
    Worker(WorkerConfig config, WorkerDependencies dependencies);

    TaskReport run_task(const fragment::PartitionInfo& partition,
                        const std::string& asm_path,
                        const std::string& binary_path,
                        const std::string& summary_path,
                        const Task& task);

    void reset_state();
    void load_initial_memory(const std::vector<MemorySnapshot>& snapshots);
    void add_observer(std::shared_ptr<TaskObserver> observer);

private:
    friend class DefaultTaskHandlerFactory;
    WorkerConfig config_;
    MemoryLut memory_lut_;
    RegisterState register_state_;
    std::unique_ptr<BackendConnector> connector_;
    std::vector<MemorySnapshot> initial_memory_;
    TaskRouter router_;
    std::map<FragmentOsAction, std::function<TaskReport(const TaskContext&, const Task&)>> action_handlers_;
    std::vector<std::shared_ptr<TaskObserver>> observers_;

    void record_memory_patches(const std::vector<fragment::MemoryPatch>& patches);
    void record_register_state(const RegisterState& regs);

    TaskReport build_report(const fragment::PartitionInfo& partition,
                            const Task& task,
                            fragment::ExecutionResult&& result);
    TaskReport run_binary_task(const TaskContext& context,
                               const Task& task);
    TaskReport run_health_task(const TaskContext& context,
                               const Task& task);
    TaskReport run_backend(const TaskContext& context,
                           const Task& task);
    TaskReport build_policy_report(const fragment::PartitionInfo& partition,
                                   const Task& task,
                                   const std::string& message);
    FragmentOsAction resolve_fragment_action(const fragment::PartitionInfo& partition) const;
    void register_action_handlers();
    void notify_task_start(const TaskContext& context, const Task& task) const;
    void notify_task_finish(const TaskContext& context, const Task& task, const TaskReport& report) const;

    std::vector<MemorySnapshot> snapshot_memory_state() const;
};

}  // namespace worker
