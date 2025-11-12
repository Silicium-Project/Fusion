#include "worker/worker.hpp"

namespace worker {

Worker::Worker(WorkerConfig config)
: config_(std::move(config)) {}

TaskReport Worker::run_task(const fragment::PartitionInfo& partition,
                            const std::string& asm_path,
                            const std::string& binary_path,
                            const Task& task) const {
    fragment::FragmentExecutor executor(config_.executor);
    if (!binary_path.empty())
        executor.set_binary_path(binary_path);
    executor.set_inputs(task.inputs);

    fragment::ExecutionEntry entry;
    entry.name = partition.id;
    entry.asm_path = asm_path;
    entry.meta = std::cref(partition);

    fragment::ExecutionResult result;
    const bool executed = fragment::execute_entry(entry,
                                                  config_.native_mode || config_.executor.use_native_execution,
                                                  executor,
                                                  result);
    if (!executed) {
        result.success = false;
        if (result.error_message.empty())
            result.error_message = "Impossible de préparer le fragment " + partition.id;
    }

    TaskReport report;
    report.partition_id = partition.id;
    report.inputs = task.inputs;
    report.result = std::move(result);
    return report;
}

}  // namespace worker
