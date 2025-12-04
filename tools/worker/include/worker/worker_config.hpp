#pragma once

#include <string>

#include "fragment/config.hpp"

namespace worker {

enum class ExecutionBackend {
    Emulator,
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
    bool native_mode = false;
    bool reset_between_tasks = false;
    ExecutionBackend backend = ExecutionBackend::Emulator;
    std::string dynamo_runner_binary = "/opt/dynamo-runner/dynamo_fragment_runner";
    std::string dynamo_launcher = "tools/worker/scripts/dynamo_runner.sh";
    ConnectorMode connector = ConnectorMode::Direct;
    std::string connector_endpoint;
};

}  // namespace worker
