#pragma once

#include <memory>
#include <string>
#include <vector>

#include "PartitionSummary.hpp"

#include "worker/backend_connector.hpp"
#include "worker/memory_lut.hpp"
#include "worker/task.hpp"
#include "worker/task_report.hpp"
#include "worker/task_types.hpp"
#include "worker/worker_config.hpp"

namespace worker {

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
    WorkerConfig config_;
    MemoryLut memory_lut_;
    RegisterState register_state_;
    std::unique_ptr<BackendConnector> connector_;
    std::vector<MemorySnapshot> initial_memory_;

    void record_memory_patches(const std::vector<fragment::MemoryPatch>& patches);
    void record_register_state(const RegisterState& regs);

    TaskReport build_report(const fragment::PartitionInfo& partition,
                            const Task& task,
                            fragment::ExecutionResult&& result);

    std::vector<MemorySnapshot> snapshot_memory_state() const;
};

}  // namespace worker
