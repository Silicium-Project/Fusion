#include "worker/backend/HttpConnector.hpp"

#include <array>
#include <atomic>
#include <cstdlib>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <stdexcept>

#if defined(_WIN32)
#include <process.h>
#else
#include <unistd.h>
#endif

#include "worker/task/TaskSerializer.hpp"

namespace worker {
namespace {

std::string read_pipe(FILE* pipe) {
    std::string result;
    std::array<char, 512> buffer{};
    while (true) {
        const size_t read = std::fread(buffer.data(), 1, buffer.size(), pipe);
        if (!read)
            break;
        result.append(buffer.data(), read);
    }
    return result;
}

std::filesystem::path make_temp_directory() {
    static std::atomic<uint64_t> counter{0};
    std::filesystem::path base = std::filesystem::temp_directory_path() / "worker_http";
    std::error_code ec;
    std::filesystem::create_directories(base, ec);
    const auto unique_id = counter.fetch_add(1, std::memory_order_relaxed);
    std::filesystem::path dir = base / ("req_" + std::to_string(getpid()) + "_" + std::to_string(unique_id));
    std::filesystem::create_directories(dir);
    return dir;
}

struct TempDirCleanup {
    std::filesystem::path path;
    ~TempDirCleanup() {
        if (path.empty())
            return;
        std::error_code ec;
        std::filesystem::remove_all(path, ec);
    }
};

void write_text_file(const std::filesystem::path& path, const std::string& content) {
    std::ofstream file(path, std::ios::out | std::ios::trunc);
    if (!file)
        throw std::runtime_error("Impossible d'écrire " + path.string());
    file << content;
}

std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("Impossible d'ouvrir " + path.string());
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

double clamp_timeout(double value, double fallback) {
    if (value <= 0.0)
        return fallback;
    return value;
}

std::string shell_escape(const std::string& input) {
    std::ostringstream oss;
    oss << '"';
    for (char c : input) {
        if (c == '"' || c == '\\')
            oss << '\\';
        oss << c;
    }
    oss << '"';
    return oss.str();
}

bool starts_with(const std::string& value, const std::string& prefix) {
    return value.size() >= prefix.size()
        && value.compare(0, prefix.size(), prefix) == 0;
}

}  // namespace

HttpConnector::HttpConnector(const WorkerConfig& config)
: config_(config) {}

fragment::ExecutionResult HttpConnector::execute(const BackendRequest& request) {
    fragment::ExecutionResult result;
    if (config_.connector_endpoint.empty()) {
        result.success = false;
        result.error_message = "Connecteur HTTP non configuré (endpoint manquant)";
        return result;
    }

    TaskPayload payload;
    payload.type = TaskType::Binary;
    payload.partition_id = request.partition.id;
    payload.asm_path = request.asm_path;
    payload.binary_path = request.binary_path;
    payload.mode = config_.mode;
    payload.inputs = request.inputs;
    payload.register_state = request.register_state;
    payload.memory_state = request.memory_state;
    payload.fd_rules = request.fd_rules;

    const std::string serialized = serialize_task_payload(payload);

    if (starts_with(config_.connector_endpoint, "file://")) {
        const std::filesystem::path path = config_.connector_endpoint.substr(7);
        try {
            const std::string content = read_text_file(path);
            return deserialize_execution_result(content);
        } catch (const std::exception& e) {
            result.success = false;
            result.error_message = e.what();
            return result;
        }
    }

    const auto temp_dir = make_temp_directory();
    TempDirCleanup cleanup{temp_dir};
    const auto payload_path = temp_dir / "payload.json";
    write_text_file(payload_path, serialized);

    const double connect_timeout = clamp_timeout(config_.connector_connect_timeout_seconds, 5.0);
    const double total_timeout = clamp_timeout(config_.connector_timeout_seconds, 30.0);
    std::ostringstream cmd;
    cmd << "curl -sS -X POST -H \"Content-Type: application/json\" "
        << "--connect-timeout " << connect_timeout << " "
        << "--max-time " << total_timeout << " "
        << "--data-binary @" << shell_escape(payload_path.string()) << " "
        << "-w \"\\n__SILICIUM_HTTP_STATUS__:%{http_code}\\n\" "
        << shell_escape(config_.connector_endpoint);

    using PipeHandle = std::unique_ptr<FILE, decltype(&pclose)>;
    PipeHandle pipe(popen(cmd.str().c_str(), "r"), &pclose);
    if (!pipe) {
        result.success = false;
        result.error_message = "Impossible d'exécuter curl";
        return result;
    }

    std::string response = read_pipe(pipe.get());
    const int rc = pclose(pipe.release());
    const std::string marker = "\n__SILICIUM_HTTP_STATUS__:";
    int http_status = 0;
    auto marker_pos = response.rfind(marker);
    if (marker_pos != std::string::npos) {
        const auto status_start = marker_pos + marker.size();
        const auto status_end = response.find('\n', status_start);
        const std::string code = response.substr(status_start, status_end - status_start);
        http_status = std::atoi(code.c_str());
        response.erase(marker_pos);
        if (!response.empty() && response.back() == '\n')
            response.pop_back();
    }

    try {
        result = deserialize_execution_result(response);
        if (http_status >= 400) {
            result.success = false;
            if (result.error_message.empty())
                result.error_message = "Erreur HTTP " + std::to_string(http_status);
            else
                result.error_message += " (http=" + std::to_string(http_status) + ")";
        }
        if (rc && result.error_message.empty()) {
            result.error_message = "Connecteur HTTP en erreur (curl=" + std::to_string(rc) + ")";
            if (http_status)
                result.error_message += ", http=" + std::to_string(http_status);
        }
    } catch (const std::exception& e) {
        result.success = false;
        result.error_message = e.what();
        if (rc)
            result.error_message += " (curl=" + std::to_string(rc) + ")";
        if (http_status)
            result.error_message += " (http=" + std::to_string(http_status) + ")";
    }

    return result;
}

}  // namespace worker
