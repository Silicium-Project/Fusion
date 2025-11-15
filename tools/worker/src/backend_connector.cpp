#include "worker/backend_connector.hpp"

#include <atomic>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>

#include "fragment/cli.hpp"
#include "fragment/fragment_executor.hpp"

#include "worker/dynamorio_runner.hpp"

namespace worker {
namespace {

class DirectConnector : public BackendConnector {
public:
    explicit DirectConnector(const WorkerConfig& config)
    : config_(config) {
        if (config_.backend == ExecutionBackend::Dynamo)
            dynamo_runner_ = std::make_unique<DynamoRunner>(config_.dynamo_launcher);
    }

    fragment::ExecutionResult execute(const BackendRequest& request) override {
        if (config_.backend == ExecutionBackend::Dynamo)
            return run_dynamo(request);
        return run_emulator(request);
    }

private:
    const WorkerConfig& config_;
    std::unique_ptr<DynamoRunner> dynamo_runner_;

    static void apply_memory_state(fragment::FragmentExecutor& executor,
                                   const std::vector<MemorySnapshot>& memory_state) {
        for (const auto& snapshot : memory_state)
            executor.apply_memory_bytes(snapshot.address, snapshot.bytes);
    }

    static void apply_register_state(fragment::FragmentExecutor& executor,
                                     const std::map<std::string, uint64_t>& register_state,
                                     const std::map<std::string, uint64_t>& overrides) {
        for (const auto& [reg, value] : register_state) {
            if (overrides.count(reg))
                continue;
            executor.set_input(reg, value);
        }
    }

    fragment::ExecutionResult run_emulator(const BackendRequest& request) const {
        fragment::FragmentExecutor executor(config_.executor);
        if (!request.binary_path.empty())
            executor.set_binary_path(request.binary_path);

        apply_memory_state(executor, request.memory_state);
        apply_register_state(executor, request.register_state, request.inputs);
        executor.set_inputs(request.inputs);

        fragment::ExecutionEntry entry;
        entry.name = request.partition.id;
        entry.asm_path = request.asm_path;
        entry.meta = std::cref(request.partition);

        fragment::ExecutionResult result;
        const bool executed = fragment::execute_entry(entry,
                                                      config_.native_mode || config_.executor.use_native_execution,
                                                      false,
                                                      executor,
                                                      result);
        if (!executed) {
            result.success = false;
            if (result.error_message.empty())
                result.error_message = "Impossible de préparer le fragment " + request.partition.id;
        }
        return result;
    }

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
            throw std::runtime_error("Impossible d'écrire " + path.string());
        file << content;
    }

    static std::string read_text_file(const std::filesystem::path& path) {
        std::ifstream file(path);
        if (!file)
            throw std::runtime_error("Impossible d'ouvrir " + path.string());
        return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    }

    static std::string to_container_path(const std::filesystem::path& host_path) {
        const auto workspace = std::filesystem::current_path();
        const auto abs = std::filesystem::absolute(host_path);
        if (!abs.string().rfind(workspace.string(), 0)) {
            auto rel = abs.lexically_relative(workspace);
            return (std::filesystem::path("/workspace") / rel).string();
        }
        return abs.string();
    }

    fragment::ExecutionResult run_dynamo(const BackendRequest& request) {
        if (!dynamo_runner_)
            throw std::runtime_error("Backend Dynamo indisponible (runner non initialisé)");
        if (config_.dynamo_runner_binary.empty())
            throw std::runtime_error("Chemin du binaire Dynamo runner non configuré");

        TaskPayload payload;
        payload.partition_id = request.partition.id;
        payload.asm_path = to_container_path(request.asm_path);
        payload.binary_path = request.binary_path.empty()
            ? std::string()
            : to_container_path(request.binary_path);
        payload.native_mode = config_.native_mode || config_.executor.use_native_execution;
        payload.inputs = request.inputs;
        payload.register_state = request.register_state;
        payload.memory_state = request.memory_state;

        const auto temp_dir = make_temp_directory();
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

        std::error_code ec;
        std::filesystem::remove_all(temp_dir, ec);
        return result;
    }
};

class HttpConnector : public BackendConnector {
public:
    explicit HttpConnector(const WorkerConfig& config)
    : config_(config) {}

    fragment::ExecutionResult execute(const BackendRequest&) override {
        fragment::ExecutionResult result;
        result.success = false;
        if (config_.connector_endpoint.empty())
            result.error_message = "Connecteur HTTP non configuré (endpoint manquant)";
        else
            result.error_message = "Connecteur HTTP non implémenté (endpoint: " + config_.connector_endpoint + ")";
        return result;
    }

private:
    const WorkerConfig& config_;
};

}  // namespace

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config) {
    switch (config.connector) {
        case ConnectorMode::Direct:
            return std::make_unique<DirectConnector>(config);
        case ConnectorMode::Http:
            return std::make_unique<HttpConnector>(config);
    }
    throw std::runtime_error("Connecteur inconnu");
}

}  // namespace worker
