#pragma once

#include <map>
#include <memory>
#include <string>
#include <vector>

#include "fragment/cli.hpp"
#include "fragment/fragment_executor.hpp"
#include "fragment/partition_summary.hpp"

#include "worker/backend_connector.hpp"
#include "worker/memory_lut.hpp"
#include "worker/types.hpp"

namespace worker {

class Worker {
public:
    explicit Worker(WorkerConfig config = {});

    TaskReport run_task(const fragment::PartitionInfo& partition,
                        const std::string& asm_path,
                        const std::string& binary_path,
                        const Task& task);

    void reset_state();
    void load_initial_memory(const std::vector<MemorySnapshot>& snapshots);

private:
    WorkerConfig config_;
    MemoryLut memory_lut_;
    std::map<std::string, uint64_t> register_state_;
    std::unique_ptr<BackendConnector> connector_;
    std::vector<MemorySnapshot> initial_memory_;

    void apply_memory_state(fragment::FragmentExecutor& executor);
    void apply_register_state(fragment::FragmentExecutor& executor, const Task& task);
    void record_memory_patches(const std::vector<fragment::MemoryPatch>& patches);
    void record_register_state(const std::map<std::string, uint64_t>& regs);

    TaskReport build_report(const fragment::PartitionInfo& partition,
                            const Task& task,
                            fragment::ExecutionResult&& result);

    std::vector<MemorySnapshot> snapshot_memory_state() const;
};

}  // namespace worker
