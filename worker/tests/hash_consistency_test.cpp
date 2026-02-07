#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

#include <gtest/gtest.h>

#include "partition/PartitionSummary.hpp"

namespace {

struct CmdResult {
    int code = 0;
    std::string stdout_data;
    std::string stderr_data;
};

CmdResult run_process(const std::vector<std::string>& args, const std::filesystem::path& cwd = {}) {
    if (args.empty())
        throw std::runtime_error("run_process: empty args");

    int out_pipe[2]{-1, -1};
    int err_pipe[2]{-1, -1};
    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0)
        throw std::runtime_error("run_process: pipe failed");

    pid_t pid = fork();
    if (pid < 0)
        throw std::runtime_error("run_process: fork failed");

    if (pid == 0) {
        if (!cwd.empty())
            chdir(cwd.c_str());
        dup2(out_pipe[1], STDOUT_FILENO);
        dup2(err_pipe[1], STDERR_FILENO);
        close(out_pipe[0]);
        close(out_pipe[1]);
        close(err_pipe[0]);
        close(err_pipe[1]);

        std::vector<char*> argv;
        argv.reserve(args.size() + 1);
        for (const auto& arg : args)
            argv.push_back(const_cast<char*>(arg.c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        _exit(127);
    }

    close(out_pipe[1]);
    close(err_pipe[1]);

    auto reader = [](int fd, std::string& out) {
        char buffer[4096];
        ssize_t n = 0;
        while ((n = read(fd, buffer, sizeof(buffer))) > 0)
            out.append(buffer, static_cast<size_t>(n));
    };

    CmdResult result;
    std::thread out_thread(reader, out_pipe[0], std::ref(result.stdout_data));
    std::thread err_thread(reader, err_pipe[0], std::ref(result.stderr_data));

    int status = 0;
    waitpid(pid, &status, 0);

    out_thread.join();
    err_thread.join();
    close(out_pipe[0]);
    close(err_pipe[0]);

    if (WIFEXITED(status))
        result.code = WEXITSTATUS(status);
    else if (WIFSIGNALED(status))
        result.code = 128 + WTERMSIG(status);
    else
        result.code = status;

    return result;
}

std::string write_text(const std::filesystem::path& path, const std::string& content) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::out | std::ios::trunc);
    out << content;
    return path.string();
}

std::string find_splitter_binary() {
    namespace fs = std::filesystem;
    const fs::path candidate = fs::absolute(fs::path("..") / "splitter" / "splitter");
    if (fs::exists(candidate))
        return candidate.lexically_normal().string();
    return {};
}

std::string build_splitter_if_needed() {
    static std::string cached;
    if (!cached.empty())
        return cached;

    auto path = find_splitter_binary();
    if (path.empty()) {
        const long cpu_count = sysconf(_SC_NPROCESSORS_ONLN);
        const auto build = run_process({"make", "splitter", "-j", std::to_string(cpu_count > 0 ? cpu_count : 4)},
                                       std::filesystem::path("..") / "splitter");
        if (build.code != 0)
            throw std::runtime_error("Failed to build splitter: " + build.stdout_data + build.stderr_data);
        path = find_splitter_binary();
        if (path.empty())
            throw std::runtime_error("splitter binary not found after build");
    }
    cached = path;
    return cached;
}

}  // namespace

TEST(HashConsistency, SplitterAndWorkerAgreeOnSummaryHash) {
    namespace fs = std::filesystem;
    const fs::path tmp_root = fs::temp_directory_path() / "hash_consistency";
    fs::create_directories(tmp_root);

    const auto src_path = tmp_root / "sample.c";
    const std::string source = R"(
        #include <stdint.h>
        int main() {
            volatile uint64_t value = 0x12345678ULL;
            return (int)(value & 0xFF);
        }
    )";
    write_text(src_path, source);

    const auto bin_path = tmp_root / "sample_bin";
    auto compile = run_process({"gcc", "-O0", "-g", "-no-pie", src_path.string(), "-o", bin_path.string()});
    ASSERT_EQ(compile.code, 0) << compile.stdout_data << compile.stderr_data;

    std::string splitter = build_splitter_if_needed();
    const auto out_dir = tmp_root / "out";
    auto split = run_process({splitter, bin_path.string(), "--output-dir", out_dir.string()});
    ASSERT_EQ(split.code, 0) << split.stdout_data << split.stderr_data;

    const auto summary_path = out_dir / "summary.json";
    ASSERT_TRUE(fs::exists(summary_path));

    fragment::PartitionSummary summary = fragment::load_partition_summary(summary_path.string(), false);
    EXPECT_FALSE(summary.summary_hash.empty());
    EXPECT_FALSE(summary.binary_hash.empty());
    EXPECT_FALSE(summary.partitions.empty());

    std::error_code ec;
    fs::remove_all(tmp_root, ec);
}
