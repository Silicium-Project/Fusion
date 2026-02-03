#include "worker/runtime/DynamoRunner.hpp"

#include <array>
#include <cstdio>
#include <filesystem>
#include <memory>
#include <sstream>
#include <stdexcept>

namespace worker {

static std::filesystem::path workspace_root() {
    auto cwd = std::filesystem::current_path();
    if (cwd.filename() == "worker")
        return cwd.parent_path();
    return cwd;
}

static std::string default_launcher() {
    namespace fs = std::filesystem;
    const fs::path relative("worker/scripts/dynamo_runner.sh");
    fs::path probe = fs::current_path();
    while (true) {
        const fs::path candidate = (probe / relative).lexically_normal();
        if (fs::exists(candidate))
            return candidate.string();
        if (!probe.has_parent_path())
            break;
        probe = probe.parent_path();
    }
    return relative.string();
}

static std::string join_arguments(const std::vector<std::string>& args) {
    std::ostringstream oss;
    for (const auto& arg : args) {
        if (!oss.str().empty())
            oss << ' ';
        oss << '"' << arg << '"';
    }
    return oss.str();
}

static std::string read_pipe(FILE* pipe) {
    std::string result;
    std::array<char, 512> buffer{};
    while (true) {
        size_t read = std::fread(buffer.data(), 1, buffer.size(), pipe);
        if (!read)
            break;
        result.append(buffer.data(), read);
    }
    return result;
}

DynamoRunner::DynamoRunner(std::string launcher_path) {
    if (launcher_path.empty())
        launcher_path_ = default_launcher();
    else
        launcher_path_ = std::move(launcher_path);
    launcher_path_ = std::filesystem::absolute(launcher_path_).string();
}

bool DynamoRunner::run_binary(const std::string& binary_path,
                              const std::vector<std::string>& args,
                              std::string& stdout_buffer,
                              std::string& stderr_buffer) const {
    namespace fs = std::filesystem;
    const fs::path workspace = workspace_root();
    const fs::path abs_binary = fs::absolute(binary_path);
    std::string container_binary = abs_binary.string();
    if (!abs_binary.string().rfind(workspace.string(), 0)) {
        const auto rel = abs_binary.lexically_relative(workspace);
        container_binary = (fs::path("/workspace") / rel).string();
    }
    const std::string args_str = join_arguments(args);

    std::ostringstream cmd;
    cmd << '"' << launcher_path_ << '"'
        << ' ' << '"' << container_binary << '"';
    if (!args.empty())
        cmd << ' ' << args_str;

    using PipeHandle = std::unique_ptr<FILE, decltype(&pclose)>;
    PipeHandle pipe(popen(cmd.str().c_str(), "r"), &pclose);
    if (!pipe)
        throw std::runtime_error("Impossible d'exécuter le lanceur DynamoRIO: " + cmd.str());

    stdout_buffer = read_pipe(pipe.get());
    const int rc = pclose(pipe.release());
    if (rc)
        stderr_buffer = "drrun a retourné " + std::to_string(rc);
    return !rc;
}

}  // namespace worker
