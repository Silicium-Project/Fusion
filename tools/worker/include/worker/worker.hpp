#pragma once

#include <string>

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
                        const Task& task) const;

private:
    WorkerConfig config_;
};

}  // namespace worker
