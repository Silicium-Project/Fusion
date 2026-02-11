#include "worker/core/Worker.hpp"

#include <algorithm>
#include <cctype>
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

static std::string lower_copy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

static std::string host_os_label() {
#if defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
    return "macos";
#elif defined(__linux__)
    return "linux";
#else
    return "unknown";
#endif
}

static std::string infer_binary_format(const fragment::PartitionInfo& partition) {
    const std::string format = lower_copy(partition.format);
    return format.empty() ? "unknown" : format;
}

static std::string infer_binary_os(const fragment::PartitionInfo& partition) {
    std::string os = lower_copy(partition.os);
    if (!os.empty())
        return os;
    const std::string format = infer_binary_format(partition);
    if (format == "pe")
        return "windows";
    if (format == "elf")
        return "linux";
    return "unknown";
}

static void fill_telemetry(TaskReport& report,
                           const Task& task,
                           const fragment::PartitionInfo& partition,
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
    report.telemetry.host_os = host_os_label();
    report.telemetry.binary_os = infer_binary_os(partition);
    report.telemetry.binary_format = infer_binary_format(partition);
    report.telemetry.linux_policy = fragment_os_action_to_string(config.fragment_os_policy.linux);
    report.telemetry.windows_policy = fragment_os_action_to_string(config.fragment_os_policy.windows);
    report.telemetry.wsl_enabled = config.wsl_enabled;
    report.telemetry.wsl_decision = config.wsl_decision;
    if (report.telemetry.required_backend.empty())
        report.telemetry.required_backend = "none";
    if (report.telemetry.routing_decision.empty())
        report.telemetry.routing_decision = "unspecified";
    if (report.telemetry.capability_matrix.empty()) {
        std::ostringstream capabilities;
        capabilities << "native=" << (config.capabilities.native ? "1" : "0")
                     << ",docker=" << (config.capabilities.docker ? "1" : "0")
                     << ",wsl=" << (config.capabilities.wsl ? "1" : "0")
                     << ",http=" << (config.capabilities.http ? "1" : "0");
        report.telemetry.capability_matrix = capabilities.str();
    }
    report.telemetry.mcp_enabled = config.mcp.read_only;
}

static bool capability_for_target(const BackendCapabilities& capabilities,
                                  BackendTarget target) {
    switch (target) {
        case BackendTarget::Native: return capabilities.native;
        case BackendTarget::Docker: return capabilities.docker;
        case BackendTarget::Wsl: return capabilities.wsl;
        case BackendTarget::Http: return capabilities.http;
        case BackendTarget::None: default: return true;
    }
}

FragmentOsAction Worker::resolve_fragment_action(const fragment::PartitionInfo& partition) const {
    const std::string os = infer_binary_os(partition);
    if (os == "linux")
        return config_.fragment_os_policy.linux;
    if (os == "windows")
        return config_.fragment_os_policy.windows;
    return FragmentOsAction::Skip;
}

Worker::Worker(WorkerConfig config)
: Worker(std::move(config), WorkerDependencies{}) {}

Worker::Worker(WorkerConfig config, std::unique_ptr<IBackendConnector> connector)
: Worker(std::move(config), WorkerDependencies{std::move(connector)}) {}

Worker::Worker(WorkerConfig config, WorkerDependencies dependencies)
: config_(std::move(config)),
  connector_(std::move(dependencies.connector)),
  observers_(std::move(dependencies.observers)) {
    auto connector_factory = std::move(dependencies.connector_factory);
    if (!connector_factory)
        connector_factory = make_backend_connector_factory();
    if (!connector_)
        connector_ = connector_factory->create(config_);

    auto handler_factory = std::move(dependencies.handler_factory);
    if (!handler_factory)
        handler_factory = make_task_handler_factory();
    handler_factory->register_handlers(router_, *this);

    register_action_handlers();
}

void Worker::set_mode(ExecutionMode mode) {
    config_.mode = mode;
}

ExecutionMode Worker::mode() const {
    return config_.mode;
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

void Worker::add_observer(std::shared_ptr<ITaskObserver> observer) {
    if (observer)
        observers_.push_back(std::move(observer));
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
    notify_task_start(context, task);
    try {
        TaskReport report = router_.execute(context, task);
        notify_task_finish(context, task, report);
        return report;
    } catch (const std::exception& ex) {
        const auto wall_start = now_ms();
        const auto steady_start = std::chrono::steady_clock::now();

        TaskReport report;
        report.partition_id = context.partition.id.empty() ? task.partition_id : context.partition.id;
        report.inputs = task.inputs;
        report.result.success = false;
        report.result.error_message = ex.what();

        const auto wall_end = now_ms();
        const auto steady_end = std::chrono::steady_clock::now();
        fill_telemetry(report, task, context.partition, config_, wall_start, wall_end, steady_start, steady_end);
        notify_task_finish(context, task, report);
        return report;
    }
}

TaskReport Worker::run_health_task(const TaskContext& context,
                                   const Task& task) {
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
            << "\"mode\":\"" << execution_mode_label(config_.mode) << "\","
            << "\"connector\":\"" << connector_label(config_.connector) << "\","
            << "\"reset_between_tasks\":" << (config_.reset_between_tasks ? "true" : "false") << ","
            << "\"wsl_enabled\":" << (config_.wsl_enabled ? "true" : "false") << ","
            << "\"wsl_decision\":\"" << config_.wsl_decision << "\","
            << "\"capabilities\":{"
            << "\"native\":" << (config_.capabilities.native ? "true" : "false") << ","
            << "\"docker\":" << (config_.capabilities.docker ? "true" : "false") << ","
            << "\"wsl\":" << (config_.capabilities.wsl ? "true" : "false") << ","
            << "\"http\":" << (config_.capabilities.http ? "true" : "false")
            << "}"
            << "}";
    report.result.program_stdout = payload.str();

    fill_telemetry(report, task, context.partition, config_, wall_start, wall_end, steady_start, steady_end);
    return report;
}

TaskReport Worker::run_binary_task(const TaskContext& context,
                                   const Task& task) {
    if (config_.reset_between_tasks)
        reset_state();

    const auto wall_start = now_ms();
    const auto steady_start = std::chrono::steady_clock::now();

    TaskReport report;

    const FragmentOsAction action = resolve_fragment_action(context.partition);
    const auto it = action_handlers_.find(action);
    if (it == action_handlers_.end())
        throw std::runtime_error("Aucun handler pour la policy OS: " + fragment_os_action_to_string(action));
    report = it->second(context, task);

    const auto wall_end = now_ms();
    const auto steady_end = std::chrono::steady_clock::now();
    fill_telemetry(report, task, context.partition, config_, wall_start, wall_end, steady_start, steady_end);

    return report;
}

TaskReport Worker::run_backend(const TaskContext& context,
                               const Task& task) {
    return run_backend(context, task, config_.mode);
}

TaskReport Worker::run_backend(const TaskContext& context,
                               const Task& task,
                               ExecutionMode mode_override) {
    BackendRequest request{
        context.partition,
        context.summary_path,
        context.asm_path,
        context.binary_path,
        mode_override,
        task.inputs,
        register_state_,
        snapshot_memory_state(),
        config_.executor.fd_rules
    };
    request.mode = mode_override;
    auto exec_result = connector_->execute(request);
    return build_report(context.partition, task, std::move(exec_result));
}

TaskReport Worker::build_policy_report(const fragment::PartitionInfo& partition,
                                       const Task& task,
                                       const std::string& message) {
    fragment::ExecutionResult result;
    result.success = false;
    result.error_message = message;
    return build_report(partition, task, std::move(result));
}

TaskReport Worker::decorate_route(TaskReport report,
                                  BackendTarget required_backend,
                                  const std::string& routing_decision) const {
    report.telemetry.required_backend = backend_target_to_string(required_backend);
    report.telemetry.routing_decision = routing_decision;
    report.telemetry.capability_matrix = capability_matrix_label();
    return report;
}

bool Worker::is_backend_supported(BackendTarget target, std::string* reason) const {
    if (capability_for_target(config_.capabilities, target))
        return true;
    if (reason)
        *reason = "capability_disabled:" + backend_target_to_string(target);
    return false;
}

BackendTarget Worker::target_for_action(FragmentOsAction action) const {
    if (action == FragmentOsAction::Wsl)
        return BackendTarget::Wsl;
    if (config_.connector == ConnectorMode::Http)
        return BackendTarget::Http;
    if (config_.mode == ExecutionMode::Dynamo)
        return BackendTarget::Docker;
    return BackendTarget::Native;
}

std::string Worker::capability_matrix_label() const {
    std::ostringstream oss;
    oss << "native=" << (config_.capabilities.native ? "1" : "0")
        << ",docker=" << (config_.capabilities.docker ? "1" : "0")
        << ",wsl=" << (config_.capabilities.wsl ? "1" : "0")
        << ",http=" << (config_.capabilities.http ? "1" : "0");
    return oss.str();
}

void Worker::register_action_handlers() {
    action_handlers_.clear();
    action_handlers_.emplace(FragmentOsAction::Skip,
                             [this](const TaskContext& context, const Task& task) {
                                 auto report = build_policy_report(
                                     context.partition,
                                     task,
                                     "Fragment ignore par la policy OS");
                                 return decorate_route(std::move(report), BackendTarget::None, "policy_skip");
                             });
    action_handlers_.emplace(FragmentOsAction::Queue,
                             [this](const TaskContext& context, const Task& task) {
                                 auto report = build_policy_report(
                                     context.partition,
                                     task,
                                     "Fragment mis en file par la policy OS");
                                 return decorate_route(std::move(report), BackendTarget::None, "policy_queue");
                             });
    action_handlers_.emplace(FragmentOsAction::Error,
                             [this](const TaskContext& context, const Task& task) {
                                 auto report = build_policy_report(
                                     context.partition,
                                     task,
                                     "Fragment refuse par la policy OS");
                                 return decorate_route(std::move(report), BackendTarget::None, "policy_error");
                             });
    action_handlers_.emplace(FragmentOsAction::Wsl,
                             [this](const TaskContext& context, const Task& task) {
                                 const BackendTarget required = target_for_action(FragmentOsAction::Wsl);
                                 if (!config_.wsl_enabled) {
                                     auto report = build_policy_report(
                                         context.partition,
                                         task,
                                         "Policy WSL demandee mais triggers inactifs");
                                     return decorate_route(std::move(report), required, "policy_wsl_triggers_disabled");
                                 }
                                 std::string reason;
                                 if (!is_backend_supported(required, &reason)) {
                                     auto report = build_policy_report(
                                         context.partition,
                                         task,
                                         "Backend non supporte pour policy WSL: " + reason);
                                     return decorate_route(std::move(report), required, "policy_wsl_unsupported");
                                 }
                                 auto report = run_backend(context, task, config_.mode);
                                 return decorate_route(std::move(report), required, "policy_wsl_execute");
                             });
    action_handlers_.emplace(FragmentOsAction::Native,
                             [this](const TaskContext& context, const Task& task) {
                                 const BackendTarget required = target_for_action(FragmentOsAction::Native);
                                 std::string reason;
                                 if (!is_backend_supported(required, &reason)) {
                                     auto report = build_policy_report(
                                         context.partition,
                                         task,
                                         "Backend non supporte pour policy native: " + reason);
                                     return decorate_route(std::move(report), required, "policy_native_unsupported");
                                 }
                                 const ExecutionMode effective_mode =
                                     (config_.connector == ConnectorMode::Direct && config_.mode == ExecutionMode::Auto)
                                         ? ExecutionMode::Native
                                         : config_.mode;
                                 auto report = run_backend(context, task, effective_mode);
                                 return decorate_route(std::move(report), required, "policy_native_execute");
                             });
}
void Worker::notify_task_start(const TaskContext& context, const Task& task) const {
    for (const auto& observer : observers_) {
        if (!observer)
            continue;
        try {
            observer->on_task_start(context, task);
        } catch (...) {
        }
    }
}

void Worker::notify_task_finish(const TaskContext& context,
                                const Task& task,
                                const TaskReport& report) const {
    for (const auto& observer : observers_) {
        if (!observer)
            continue;
        try {
            observer->on_task_finish(context, task, report);
        } catch (...) {
        }
    }
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

