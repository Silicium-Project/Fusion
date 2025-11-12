#include "worker/worker.hpp"

namespace worker {

Worker::Worker(WorkerConfig config)
: config_(std::move(config)) {}

void Worker::reset_state() {
    memory_state_.clear();
    register_state_.clear();
}

void Worker::apply_memory_state(fragment::FragmentExecutor& executor) {
    for (const auto& [address, bytes] : memory_state_)
        executor.apply_memory_bytes(address, bytes);
}

void Worker::record_memory_patches(const std::vector<fragment::MemoryPatch>& patches) {
    for (const auto& patch : patches)
        memory_state_[patch.address] = patch.after;
}

void Worker::apply_register_state(fragment::FragmentExecutor& executor, const Task& task) {
    for (const auto& [reg, value] : register_state_) {
        if (task.inputs.count(reg))
            continue;
        executor.set_input(reg, value);
    }
}

void Worker::record_register_state(const std::map<std::string, uint64_t>& regs) {
    register_state_ = regs;
}

TaskReport Worker::run_task(const fragment::PartitionInfo& partition,
                            const std::string& asm_path,
                            const std::string& binary_path,
                            const Task& task) {
    if (config_.reset_between_tasks)
        reset_state();

    fragment::FragmentExecutor executor(config_.executor);

    if (!binary_path.empty())
        executor.set_binary_path(binary_path);

    if (!config_.reset_between_tasks)
        apply_memory_state(executor);

    if (!config_.reset_between_tasks)
        apply_register_state(executor, task);

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
    if (!config_.reset_between_tasks && report.result.success) {
        record_memory_patches(report.result.memory_patches);
        record_register_state(report.result.final_regs);
    }

    return report;
}

}  // namespace worker
