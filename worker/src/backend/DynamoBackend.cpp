#include "worker/backend/DynamoBackend.hpp"

#include <atomic>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <unistd.h>

namespace worker {

static std::filesystem::path make_temp_directory() {
    static std::atomic<uint64_t> counter{0};
    std::filesystem::path base = std::filesystem::current_path() / ".worker_tmp";
    std::error_code ec;
    std::filesystem::create_directories(base, ec);
    const auto unique_id = counter.fetch_add(1, std::memory_order_relaxed);
    std::filesystem::path dir = base / ("worker_conn_" + std::to_string(getpid()) + "_" + std::to_string(unique_id));
    std::filesystem::create_directories(dir);
    return dir;
}

static void write_text_file(const std::filesystem::path& path, const std::string& content) {
    std::ofstream file(path, std::ios::out | std::ios::trunc);
    if (!file)
        throw std::runtime_error("Impossible d'Ã©crire " + path.string());
    file << content;
}

static std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("Impossible d'ouvrir " + path.string());
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

static std::string to_container_path(const std::filesystem::path& host_path) {
    auto workspace = std::filesystem::current_path();
    if (workspace.filename() == "worker")
        workspace = workspace.parent_path();
    const auto abs = std::filesystem::absolute(host_path);
    if (!abs.string().rfind(workspace.string(), 0)) {
        auto rel = abs.lexically_relative(workspace);
        return (std::filesystem::path("/workspace") / rel).string();
    }
    return abs.string();
}

DynamoBackend::DynamoBackend(const WorkerConfig& config)
: config_(config),
  dynamo_runner_(std::make_unique<DynamoRunner>(config.dynamo_launcher)) {
    namespace fs = std::filesystem;
    if (config_.dynamo_runner_binary.empty())
        throw std::runtime_error("Chemin du binaire Dynamo runner non configurÃ©");
    const fs::path host_runner = fs::absolute(config_.dynamo_runner_binary);
    if (!fs::exists(host_runner)) {
        throw std::runtime_error("Binaire Dynamo runner introuvable: " + host_runner.string() +
                                 " (build: make worker ou docker build -t dynamorio-runner infra/docker/dynamorio-runner)");
    }
}

fragment::ExecutionResult DynamoBackend::execute(const BackendRequest& request) {
    if (!dynamo_runner_)
        throw std::runtime_error("Backend Dynamo indisponible (runner non initialisÃ©)");
    if (config_.dynamo_runner_binary.empty())
        throw std::runtime_error("Chemin du binaire Dynamo runner non configurÃ©");

    TaskPayload payload;
    payload.type = TaskType::Binary;
    payload.partition_id = request.partition.id;
    payload.asm_path = to_container_path(request.asm_path);
    payload.binary_path = request.binary_path.empty()
        ? std::string()
        : to_container_path(request.binary_path);
    payload.mode = ExecutionMode::Native;  // prioritÃ© au natif dans DynamoRIO
    payload.inputs = request.inputs;
    payload.register_state = request.register_state;
    payload.memory_state = request.memory_state;
    payload.fd_rules = request.fd_rules;

    const auto temp_dir = make_temp_directory();
    auto cleanup = std::unique_ptr<void, std::function<void(void*)>>(
        reinterpret_cast<void*>(1),
        [temp_dir](void*) {
            if (temp_dir.empty())
                return;
            std::error_code ec;
            std::filesystem::remove_all(temp_dir, ec);
        });
    const auto input_path = temp_dir / "input.json";
    const auto output_path = temp_dir / "output.json";

    write_text_file(input_path, serialize_task_payload(payload));

    const std::string container_input = to_container_path(input_path);
    const std::string container_output = to_container_path(output_path);

    std::vector<std::string> args = {"--input", container_input, "--output", container_output};
    std::string dyn_stdout;
    std::string dyn_stderr;
    const bool ok = dynamo_runner_->run_binary(config_.dynamo_runner_binary,
                                               args,
                                               dyn_stdout,
                                               dyn_stderr);
    if (!dyn_stdout.empty())
        std::cout << dyn_stdout;
    if (!dyn_stderr.empty())
        std::cerr << dyn_stderr << '\n';

    fragment::ExecutionResult result;
    try {
        const std::string output_text = read_text_file(output_path);
        result = deserialize_execution_result(output_text);
        if (!ok && result.error_message.empty())
            result.error_message = "Execution DynamoRIO en erreur";
    } catch (const std::exception& e) {
        result.success = false;
        result.error_message = e.what();
    }

    return result;
}

}  // namespace worker
