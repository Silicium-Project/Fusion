#pragma once

#include <string>

#include <map>

#include "fragment/cli.hpp"
#include "fragment/fragment_executor.hpp"
#include "fragment/partition_summary.hpp"

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

private:
    WorkerConfig config_;
    std::map<uint64_t, std::vector<uint8_t>> memory_state_;
    std::map<std::string, uint64_t> register_state_;

    void apply_memory_state(fragment::FragmentExecutor& executor);
    void apply_register_state(fragment::FragmentExecutor& executor, const Task& task);
    void record_memory_patches(const std::vector<fragment::MemoryPatch>& patches);
    void record_register_state(const std::map<std::string, uint64_t>& regs);
};

}  // namespace worker
