#pragma once

#include <string>

#include "Config.hpp"

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
};

}  // namespace worker
