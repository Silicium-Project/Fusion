#include "worker/core/Worker.hpp"

#include <chrono>
#include <sstream>

namespace worker {

static std::uint64_t now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

static std::string execution_mode_label(ExecutionMode mode) {
    switch (mode) {
        case ExecutionMode::Dynamo: return "dynamo";
        case ExecutionMode::Native: return "native";
        case ExecutionMode::Emulator: return "emu";
        case ExecutionMode::Auto: default: return "auto";
    }
}

static std::string connector_label(ConnectorMode mode) {
    switch (mode) {
        case ConnectorMode::Http: return "http";
        case ConnectorMode::Direct: default: return "direct";
    }
}

static void fill_telemetry(TaskReport& report,
                           const Task& task,
                           const WorkerConfig& config,
                           std::uint64_t wall_start,
                           std::uint64_t wall_end,
                           std::chrono::steady_clock::time_point steady_start,
                           std::chrono::steady_clock::time_point steady_end) {
    std::string task_id = task.partition_id.empty() ? report.partition_id : task.partition_id;
    if (task_id.empty())
        task_id = "task";
    report.telemetry.task_id = task_id;
    report.telemetry.type = task.type;
    report.telemetry.status = report.result.success ? "success" : "failure";
    report.telemetry.started_at_ms = wall_start;
    report.telemetry.finished_at_ms = wall_end;
    report.telemetry.duration_ms =
        static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(steady_end - steady_start).count());
    report.telemetry.linux_policy = fragment_os_action_to_string(config.fragment_os_policy.linux);
    report.telemetry.windows_policy = fragment_os_action_to_string(config.fragment_os_policy.windows);
}

class BinaryTaskHandler : public TaskHandler {
public:
    explicit BinaryTaskHandler(Worker& worker)
    : worker_(worker) {}

    TaskReport handle(const TaskContext& context, const Task& task) override {
        return worker_.run_binary_task(context, task);
    }

private:
    Worker& worker_;
};

class HealthTaskHandler : public TaskHandler {
public:
    explicit HealthTaskHandler(Worker& worker)
    : worker_(worker) {}

    TaskReport handle(const TaskContext& context, const Task& task) override {
        const auto wall_start = now_ms();
        const auto steady_start = std::chrono::steady_clock::now();

        TaskReport report;
        report.partition_id = context.partition.id.empty()
            ? (task.partition_id.empty() ? "health" : task.partition_id)
            : context.partition.id;
        report.inputs = task.inputs;
        report.result.success = true;

        const auto wall_end = now_ms();
        const auto steady_end = std::chrono::steady_clock::now();

        std::ostringstream payload;
        payload << "{"
                << "\"status\":\"ok\","
                << "\"version\":\"unknown\","
                << "\"timestamp_ms\":" << wall_end << ","
                << "\"mode\":\"" << execution_mode_label(worker_.config_.mode) << "\","
                << "\"connector\":\"" << connector_label(worker_.config_.connector) << "\","
                << "\"reset_between_tasks\":" << (worker_.config_.reset_between_tasks ? "true" : "false")
                << "}";
        report.result.program_stdout = payload.str();

        fill_telemetry(report, task, worker_.config_, wall_start, wall_end, steady_start, steady_end);
        return report;
    }

private:
    Worker& worker_;
};

Worker::Worker(WorkerConfig config)
: Worker(std::move(config), {}) {}

Worker::Worker(WorkerConfig config, std::unique_ptr<BackendConnector> connector)
: config_(std::move(config)), connector_(std::move(connector)) {
    if (!connector_)
        connector_ = make_backend_connector(config_);
    router_.register_handler(TaskType::Binary, std::make_unique<BinaryTaskHandler>(*this));
    router_.register_handler(TaskType::Health, std::make_unique<HealthTaskHandler>(*this));
}

void Worker::reset_state() {
    memory_lut_.clear();
    register_state_.clear();
    if (!initial_memory_.empty())
        memory_lut_.seed(initial_memory_);
}

void Worker::load_initial_memory(const std::vector<MemorySnapshot>& snapshots) {
    initial_memory_ = snapshots;
    memory_lut_.clear();
    memory_lut_.seed(initial_memory_);
}

void Worker::record_memory_patches(const std::vector<fragment::MemoryPatch>& patches) {
    for (const auto& patch : patches)
        memory_lut_.apply_patch(patch);
}

void Worker::record_register_state(const RegisterState& regs) {
    register_state_ = regs;
}

std::vector<MemorySnapshot> Worker::snapshot_memory_state() const {
    return memory_lut_.snapshot();
}

TaskReport Worker::run_task(const fragment::PartitionInfo& partition,
                            const std::string& asm_path,
                            const std::string& binary_path,
                            const std::string& summary_path,
                            const Task& task) {
    TaskContext context{
        partition,
        asm_path,
        binary_path,
        summary_path
    };
    return router_.execute(context, task);
}

TaskReport Worker::run_binary_task(const TaskContext& context,
                                   const Task& task) {
    if (config_.reset_between_tasks)
        reset_state();

    const auto wall_start = now_ms();
    const auto steady_start = std::chrono::steady_clock::now();

    BackendRequest request{
        context.partition,
        context.summary_path,
        context.asm_path,
        context.binary_path,
        task.inputs,
        register_state_,
        snapshot_memory_state(),
        config_.executor.fd_rules
    };

    auto result = connector_->execute(request);
    TaskReport report = build_report(context.partition, task, std::move(result));

    const auto wall_end = now_ms();
    const auto steady_end = std::chrono::steady_clock::now();
    fill_telemetry(report, task, config_, wall_start, wall_end, steady_start, steady_end);

    return report;
}

TaskReport Worker::build_report(const fragment::PartitionInfo& partition,
                                const Task& task,
                                fragment::ExecutionResult&& result) {
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
