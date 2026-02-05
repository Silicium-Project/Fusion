#pragma once

#include <memory>
#include <string>
#include <vector>

#include "partition/PartitionSummary.hpp"

#include "worker/backend/BackendConnector.hpp"
#include "worker/state/MemoryLut.hpp"
#include "worker/task/Task.hpp"
#include "worker/task/TaskReport.hpp"
#include "worker/task/TaskTypes.hpp"
#include "worker/core/TaskRouter.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class BinaryTaskHandler;
class HealthTaskHandler;

class Worker {
public:
    explicit Worker(WorkerConfig config = {});
    Worker(WorkerConfig config, std::unique_ptr<BackendConnector> connector);

    TaskReport run_task(const fragment::PartitionInfo& partition,
                        const std::string& asm_path,
                        const std::string& binary_path,
                        const std::string& summary_path,
                        const Task& task);

    void reset_state();
    void load_initial_memory(const std::vector<MemorySnapshot>& snapshots);

private:
    friend class BinaryTaskHandler;
    friend class HealthTaskHandler;

    WorkerConfig config_;
    MemoryLut memory_lut_;
    RegisterState register_state_;
    std::unique_ptr<BackendConnector> connector_;
    std::vector<MemorySnapshot> initial_memory_;
    TaskRouter router_;

    void record_memory_patches(const std::vector<fragment::MemoryPatch>& patches);
    void record_register_state(const RegisterState& regs);

    TaskReport build_report(const fragment::PartitionInfo& partition,
                            const Task& task,
                            fragment::ExecutionResult&& result);
    TaskReport run_binary_task(const TaskContext& context,
                               const Task& task);
    FragmentOsAction resolve_fragment_action(const fragment::PartitionInfo& partition) const;

    std::vector<MemorySnapshot> snapshot_memory_state() const;
};

}  // namespace worker
