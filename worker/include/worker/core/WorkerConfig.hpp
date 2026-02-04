#pragma once

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
    std::string emulator_library = "../executor/libfragment_emulator.so";
    std::string native_library = "../executor/libfragment_executor.so";
    FragmentOsPolicy fragment_os_policy{};
};

}  // namespace worker
