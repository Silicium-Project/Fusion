#include "worker/backend_connector.hpp"

#include <atomic>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>

#include "PartitionSummary.hpp"
#include "worker/dynamorio_runner.hpp"
#include "worker/executor_client.hpp"

namespace worker {
namespace {

class IExecutionBackend {
public:
    virtual ~IExecutionBackend() = default;
    virtual fragment::ExecutionResult execute(const BackendRequest& request) = 0;
};

class LibraryBackend : public IExecutionBackend {
public:
    LibraryBackend(const WorkerConfig& config,
                   std::string library_path,
                   bool native_mode,
                   bool force_native)
    : client_(std::make_unique<ExecutorClient>(std::move(library_path)))
    , native_mode_(native_mode)
    , force_native_(force_native) {
        (void)config;
    }

    fragment::ExecutionResult execute(const BackendRequest& request) override {
        if (!client_)
            throw std::runtime_error("Backend d'exécution indisponible");
        return client_->run(request, native_mode_, force_native_);
    }

private:
    std::unique_ptr<ExecutorClient> client_;
    bool native_mode_;
    bool force_native_;
};

class DynamoBackend : public IExecutionBackend {
public:
    explicit DynamoBackend(const WorkerConfig& config)
    : config_(config),
      dynamo_runner_(std::make_unique<DynamoRunner>(config.dynamo_launcher)) {
        namespace fs = std::filesystem;
        if (config_.dynamo_runner_binary.empty())
            throw std::runtime_error("Chemin du binaire Dynamo runner non configuré");
        const fs::path host_runner = fs::absolute(config_.dynamo_runner_binary);
        if (!fs::exists(host_runner)) {
            throw std::runtime_error("Binaire Dynamo runner introuvable: " + host_runner.string() +
                                     " (build: make worker ou docker build -t dynamorio-runner infra/docker/dynamorio-runner)");
        }
    }

    fragment::ExecutionResult execute(const BackendRequest& request) override {
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
        payload.mode = ExecutionMode::Native;  // priorité au natif dans DynamoRIO
        payload.inputs = request.inputs;
        payload.register_state = request.register_state;
        payload.memory_state = request.memory_state;
        payload.fd_rules = request.fd_rules;

        const auto temp_dir = make_temp_directory();
        struct TempCleaner {
            std::filesystem::path dir;
            ~TempCleaner() {
                if (dir.empty())
                    return;
                std::error_code ec;
                std::filesystem::remove_all(dir, ec);
            }
        } cleaner{temp_dir};
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

private:
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

    const WorkerConfig& config_;
    std::unique_ptr<DynamoRunner> dynamo_runner_;
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

class DirectConnector : public BackendConnector {
public:
    explicit DirectConnector(const WorkerConfig& config)
    : config_(config) {
        emulator_ = std::make_unique<LibraryBackend>(config_, config_.emulator_library, false, false);
        native_ = std::make_unique<LibraryBackend>(config_, config_.native_library, true, true);
        if (!config_.dynamo_runner_binary.empty())
            dynamo_ = std::make_unique<DynamoBackend>(config_);
    }

    fragment::ExecutionResult execute(const BackendRequest& request) override {
        switch (config_.mode) {
            case ExecutionMode::Dynamo:
                if (dynamo_) return dynamo_->execute(request);
                throw std::runtime_error("Mode Dynamo requis mais runner indisponible");
            case ExecutionMode::Native:
                return native_->execute(request);
            case ExecutionMode::Emulator:
                return emulator_->execute(request);
            case ExecutionMode::Auto:
            default:
                if (dynamo_) return dynamo_->execute(request);
                return native_->execute(request);
        }
    }

private:
    const WorkerConfig& config_;
    std::unique_ptr<IExecutionBackend> emulator_;
    std::unique_ptr<IExecutionBackend> native_;
    std::unique_ptr<IExecutionBackend> dynamo_;
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
