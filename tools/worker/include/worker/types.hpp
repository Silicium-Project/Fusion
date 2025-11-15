#pragma once

#include <map>
#include <string>
#include <vector>

#include "fragment/config.hpp"
#include "fragment/execution_result.hpp"

namespace worker {

struct Task {
    std::string partition_id;
    std::map<std::string, uint64_t> inputs;
};

enum class ExecutionBackend {
    Emulator,
    Dynamo,
};

enum class ConnectorMode {
    Direct,
    Http,
};

struct WorkerConfig {
    WorkerConfig()
    : executor()
    , native_mode(false)
    , reset_between_tasks(false)
    , backend(ExecutionBackend::Emulator)
    , dynamo_runner_binary("/opt/dynamo-runner/dynamo_fragment_runner")
    , dynamo_launcher("tools/worker/scripts/dynamo_runner.sh")
    , connector(ConnectorMode::Direct)
    , connector_endpoint() {}

    fragment::ExecutorConfig executor;
    bool native_mode;
    bool reset_between_tasks;
    ExecutionBackend backend;
    std::string dynamo_runner_binary;
    std::string dynamo_launcher;
    ConnectorMode connector;
    std::string connector_endpoint;
};

struct TaskReport {
    std::string partition_id;
    std::map<std::string, uint64_t> inputs;
    fragment::ExecutionResult result;
};

struct WorkerReport {
    std::string summary_path;
    bool native_mode = false;
    std::vector<TaskReport> tasks;
};

}  // namespace worker
