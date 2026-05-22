#include "worker/runtime/DynamoRunner.hpp"

#include <array>
#include <atomic>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <stdexcept>

#ifdef __unix__
#include <sys/wait.h>
#endif

namespace worker {

namespace {

std::string shell_quote(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 2);
    out.push_back('\'');
    for (char c : value) {
        if (c == '\'')
            out.append("'\\''");
        else
            out.push_back(c);
    }
    out.push_back('\'');
    return out;
}

std::string join_quoted(const std::vector<std::string>& args) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& arg : args) {
        if (!first)
            oss << ' ';
        first = false;
        oss << shell_quote(arg);
    }
    return oss.str();
}

std::filesystem::path make_temp_stderr_path() {
    static std::atomic<uint64_t> counter{0};
    const auto base = std::filesystem::temp_directory_path();
    for (int i = 0; i < 10; ++i) {
        const auto id = counter.fetch_add(1, std::memory_order_relaxed);
        auto path = base / ("dynamo_stderr_" + std::to_string(id) + ".log");
        if (!std::filesystem::exists(path))
            return path;
    }
    return base / "dynamo_stderr_fallback.log";
}

std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::in | std::ios::binary);
    if (!file)
        return {};
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

struct TempFileCleanup {
    std::filesystem::path path;
    ~TempFileCleanup() {
        if (path.empty())
            return;
        std::error_code ec;
        std::filesystem::remove(path, ec);
    }
};

}  // namespace

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
    const auto rel = abs_binary.lexically_relative(workspace);
    const std::string rel_str = rel.generic_string();
    if (!rel.empty()
        && !rel.is_absolute()
        && !rel_str.empty()
        && rel_str.rfind("..", 0) != 0
        && rel_str.find("../") == std::string::npos) {
        container_binary = (fs::path("/workspace") / rel).generic_string();
    }
    const std::string args_str = join_quoted(args);
    const auto stderr_path = make_temp_stderr_path();
    TempFileCleanup stderr_cleanup{stderr_path};

    std::ostringstream cmd;
    cmd << shell_quote(launcher_path_)
        << ' ' << shell_quote(container_binary);
    if (!args.empty() && !args_str.empty())
        cmd << ' ' << args_str;
    cmd << " 2> " << shell_quote(stderr_path.string());

    using PipeHandle = std::unique_ptr<FILE, decltype(&pclose)>;
    PipeHandle pipe(popen(cmd.str().c_str(), "r"), &pclose);
    if (!pipe)
        throw std::runtime_error("Impossible d'exécuter le lanceur DynamoRIO: " + cmd.str());

    stdout_buffer = read_pipe(pipe.get());
    const int raw_status = pclose(pipe.release());
    int exit_code = raw_status;
#ifdef __unix__
    if (raw_status != -1) {
        if (WIFEXITED(raw_status)) {
            exit_code = WEXITSTATUS(raw_status);
        } else if (WIFSIGNALED(raw_status)) {
            exit_code = 128 + WTERMSIG(raw_status);
        }
    }
#endif
    stderr_buffer = read_text_file(stderr_path);
    if (exit_code)
        if (stderr_buffer.empty())
            stderr_buffer = "drrun a retourne " + std::to_string(exit_code);
    return !exit_code;
}

}  // namespace worker
