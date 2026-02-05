#pragma once

#include <sstream>
#include <stdexcept>
#include <string>

#include "core/Config.hpp"

namespace worker {

enum class ExecutionMode {
    Auto,
    Emulator,
    Native,
    Dynamo,
};

enum class ConnectorMode {
    Direct,
    Http,
};

enum class FragmentOsAction {
    Native,
    Wsl,
    Skip,
    Error,
    Queue,
};

inline std::string fragment_os_action_to_string(FragmentOsAction action) {
    switch (action) {
        case FragmentOsAction::Native: return "native";
        case FragmentOsAction::Wsl: return "wsl";
        case FragmentOsAction::Skip: return "skip";
        case FragmentOsAction::Error: return "error";
        case FragmentOsAction::Queue: return "queue";
        default: return "skip";
    }
}

inline FragmentOsAction parse_fragment_os_action(const std::string& value) {
    if (value == "native")
        return FragmentOsAction::Native;
    if (value == "wsl")
        return FragmentOsAction::Wsl;
    if (value == "skip")
        return FragmentOsAction::Skip;
    if (value == "error")
        return FragmentOsAction::Error;
    if (value == "queue")
        return FragmentOsAction::Queue;
    throw std::runtime_error("Politique fragment invalide: " + value);
}

inline FragmentOsAction default_linux_fragment_action() {
#ifdef _WIN32
    return FragmentOsAction::Skip;
#else
    return FragmentOsAction::Native;
#endif
}

inline FragmentOsAction default_windows_fragment_action() {
#ifdef _WIN32
    return FragmentOsAction::Native;
#else
    return FragmentOsAction::Skip;
#endif
}

struct FragmentOsPolicy {
    FragmentOsAction linux = default_linux_fragment_action();
    FragmentOsAction windows = default_windows_fragment_action();
};

struct WslTriggerConfig {
    bool enabled = false;
    double min_reward = 0.0;
    std::uint64_t min_jobs = 0;
    double current_reward = 0.0;
    std::uint64_t available_jobs = 0;
};

inline bool evaluate_wsl_triggers(const WslTriggerConfig& config, std::string* reason = nullptr) {
    if (!config.enabled) {
        if (reason)
            *reason = "disabled";
        return false;
    }
    if (config.current_reward < config.min_reward) {
        if (reason)
            *reason = "reward_below_threshold";
        return false;
    }
    if (config.available_jobs < config.min_jobs) {
        if (reason)
            *reason = "jobs_below_threshold";
        return false;
    }
    if (reason)
        *reason = "enabled";
    return true;
}

class WorkerConfig {
public:
    WorkerConfig() = default;

    fragment::ExecutorConfig executor{};
    bool reset_between_tasks = false;
    ExecutionMode mode = ExecutionMode::Auto;
    std::string dynamo_runner_binary;
    std::string dynamo_launcher = "worker/scripts/dynamo_runner.sh";
    ConnectorMode connector = ConnectorMode::Direct;
    std::string connector_endpoint;
    double connector_connect_timeout_seconds = 5.0;
    double connector_timeout_seconds = 30.0;
    std::string emulator_library = "../executor/libfragment_emulator.so";
    std::string native_library = "../executor/libfragment_executor.so";
    FragmentOsPolicy fragment_os_policy{};
    WslTriggerConfig wsl_triggers{};
    bool wsl_enabled = false;
    std::string wsl_decision;
};

}  // namespace worker
