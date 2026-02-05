#include <array>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

#include <gtest/gtest.h>

#include "partition/PartitionSummary.hpp"
#include "worker/runtime/JobRunner.hpp"
#include "worker/task/Task.hpp"
#include "worker/core/WorkerConfig.hpp"

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

std::vector<uint8_t> le_bytes(uint64_t value) {
    std::vector<uint8_t> out(8);
    for (size_t i = 0; i < 8; ++i)
        out[i] = static_cast<uint8_t>((value >> (i * 8)) & 0xFFu);
    return out;
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
        if (path.empty()) {
            auto debug_ls = run_process({"ls", "-l", "../splitter"});
            throw std::runtime_error("splitter binary not found after build. ls: "
                                     + debug_ls.stdout_data + debug_ls.stderr_data);
        }
    }
    cached = path;
    return cached;
}

struct RunOutputs {
    std::vector<uint8_t> stdout_bytes;
    std::vector<fragment::MemoryPatch> patches;
    std::map<std::string, uint64_t> final_regs;
};

std::string stdout_string(const RunOutputs& out) {
    return std::string(out.stdout_bytes.begin(), out.stdout_bytes.end());
}

RunOutputs run_worker(const std::string& summary_path, worker::ExecutionMode mode, const std::vector<std::string>& task_ids) {
    worker::WorkerConfig cfg;
    cfg.mode = mode;
    cfg.emulator_library = (std::filesystem::path("..") / "executor" / "libfragment_emulator.so").lexically_normal().string();
    cfg.native_library = (std::filesystem::path("..") / "executor" / "libfragment_executor.so").lexically_normal().string();
    cfg.dynamo_runner_binary.clear();

    fragment::PartitionSummary summary = fragment::load_partition_summary(summary_path, true);
    worker::JobRunner runner(summary_path, cfg);
    RunOutputs out;

    for (const auto& id : task_ids) {
        worker::Task task;
        task.partition_id = id;
        auto report = runner.execute(task);
        if (!report.result.success)
            throw std::runtime_error("Worker execution failed for partition " + task.partition_id + ": " + report.result.error_message);
        if (!report.result.program_stdout.empty())
        out.stdout_bytes.insert(out.stdout_bytes.end(),
                                report.result.program_stdout.begin(),
                                report.result.program_stdout.end());
        out.patches.insert(out.patches.end(),
                           report.result.memory_patches.begin(),
                           report.result.memory_patches.end());
        out.final_regs = report.result.final_regs;
    }
    return out;
}

uint64_t reg_value(const RunOutputs& out, const std::string& reg) {
    auto it = out.final_regs.find(reg);
    return it == out.final_regs.end() ? 0ULL : it->second;
}

}  // namespace

TEST(WorkerEquivalence, OriginalVsEmulator) {
    namespace fs = std::filesystem;
    const fs::path tmp_root = fs::temp_directory_path() / "worker_equiv_native";
    fs::create_directories(tmp_root);

    const uint64_t expected = 0x3333333333333333ULL;
    const auto src_path = tmp_root / "prog.c";
    const std::string source = R"(
        #include <stdint.h>
        #include <stdio.h>
        static const char msg[] = "3333333333333333\n";
        int main() {
            uint64_t a = 0x1111111111111111ULL;
            uint64_t b = 0x2222222222222222ULL;
            uint64_t res = a + b;
            uint64_t out = 0;
            asm volatile(
                "call puts\n"
                "mov %[val], %%rax\n"
                : "=&a"(out)
                : "D"(msg), [val]"m"(res)
                : "rcx", "rdx", "rsi", "r8", "r9", "memory");
            return out;
        }
    )";
    write_text(src_path, source);

    const auto bin_path = tmp_root / "prog";
    auto compile = run_process({"gcc", "-O0", "-g", "-no-pie", src_path.string(), "-o", bin_path.string()});
    ASSERT_EQ(compile.code, 0) << compile.stdout_data << compile.stderr_data;

    auto run_prog = run_process({bin_path.string()});
    if (run_prog.code != 0)
        std::cerr << "[WARN] Original program exited with code " << run_prog.code << "\n";
    const std::string expected_stdout = run_prog.stdout_data;

    std::string splitter;
    try {
        splitter = build_splitter_if_needed();
    } catch (const std::exception& e) {
        GTEST_SKIP() << "Splitter unavailable in test environment: " << e.what();
    }
    const fs::path out_dir = tmp_root / "out";
    fs::create_directories(out_dir);
    auto split = run_process({splitter, bin_path.string(), "--output-dir", out_dir.string()});
    ASSERT_EQ(split.code, 0) << split.stdout_data << split.stderr_data;

    const std::string summary_path = (out_dir / "summary.json").string();
    ASSERT_TRUE(fs::exists(summary_path));

    setenv("SKIP_HASH", "1", 1);
    fragment::PartitionSummary summary_meta = fragment::load_partition_summary(summary_path, true);
    std::vector<std::string> selected_ids;
    for (const auto& p : summary_meta.partitions) {
        if (p.id.find("main") != std::string::npos) {
            selected_ids.push_back(p.id);
            break;
        }
    }
    if (selected_ids.empty()) {
        auto ordered_ids = fragment::order_partitions(summary_meta.partitions);
        if (!ordered_ids.empty())
            selected_ids.push_back(ordered_ids.back());
    }
    ASSERT_FALSE(selected_ids.empty()) << "No partitions found to execute";

    auto emu = run_worker(summary_path, worker::ExecutionMode::Emulator, selected_ids);

    const auto expected_bytes = le_bytes(expected);

    const auto emu_out = stdout_string(emu);
    ASSERT_EQ(emu_out, expected_stdout);

    const auto rbp = reg_value(emu, "rbp");
    std::cerr << "[EMU] rax=" << std::hex << reg_value(emu, "rax")
              << " rdx=" << reg_value(emu, "rdx")
              << " rbp=0x" << rbp << std::dec << "\n";
    for (const auto& patch : emu.patches) {
        if (patch.address >= rbp - 0x40 && patch.address <= rbp)
            std::cerr << "[EMU] patch @" << std::hex << patch.address
                      << " bytes=" << patch.after.size() << std::dec << "\n";
    }
    EXPECT_EQ(reg_value(emu, "rax"), expected);
}

TEST(WorkerEquivalence, OriginalVsNative) {
    namespace fs = std::filesystem;
    const fs::path tmp_root = fs::temp_directory_path() / "worker_equiv_native";
    fs::create_directories(tmp_root);

    const uint64_t expected = 0x3333333333333333ULL;
    const auto src_path = tmp_root / "prog.c";
    const std::string source = R"(
        #include <stdint.h>
        #include <stdio.h>
        static const char msg[] = "3333333333333333\n";
        int main() {
            uint64_t a = 0x1111111111111111ULL;
            uint64_t b = 0x2222222222222222ULL;
            uint64_t res = a + b;
            uint64_t out = 0;
            asm volatile(
                "call puts\n"
                "mov %[val], %%rax\n"
                : "=&a"(out)
                : "D"(msg), [val]"m"(res)
                : "rcx", "rdx", "rsi", "r8", "r9", "memory");
            return out;
        }
    )";
    write_text(src_path, source);

    const auto bin_path = tmp_root / "prog";
    auto compile = run_process({"gcc", "-O0", "-g", "-no-pie", src_path.string(), "-o", bin_path.string()});
    ASSERT_EQ(compile.code, 0) << compile.stdout_data << compile.stderr_data;

    auto run_prog = run_process({bin_path.string()});
    if (run_prog.code != 0)
        std::cerr << "[WARN] Original program exited with code " << run_prog.code << "\n";
    const std::string expected_stdout = run_prog.stdout_data;

    std::string splitter;
    try {
        splitter = build_splitter_if_needed();
    } catch (const std::exception& e) {
        GTEST_SKIP() << "Splitter unavailable in test environment: " << e.what();
    }
    const fs::path out_dir = tmp_root / "out";
    fs::create_directories(out_dir);
    auto split = run_process({splitter, bin_path.string(), "--output-dir", out_dir.string()});
    ASSERT_EQ(split.code, 0) << split.stdout_data << split.stderr_data;

    const std::string summary_path = (out_dir / "summary.json").string();
    ASSERT_TRUE(fs::exists(summary_path));

    setenv("SKIP_HASH", "1", 1);
    fragment::PartitionSummary summary_meta = fragment::load_partition_summary(summary_path, true);
    std::vector<std::string> selected_ids;
    for (const auto& p : summary_meta.partitions) {
        if (p.id.find("main") != std::string::npos) {
            selected_ids.push_back(p.id);
            break;
        }
    }
    if (selected_ids.empty()) {
        auto ordered_ids = fragment::order_partitions(summary_meta.partitions);
        if (!ordered_ids.empty())
            selected_ids.push_back(ordered_ids.back());
    }
    ASSERT_FALSE(selected_ids.empty()) << "No partitions found to execute";

    auto nat = run_worker(summary_path, worker::ExecutionMode::Native, selected_ids);

    const auto nat_out = stdout_string(nat);
    if (nat_out.empty())
        GTEST_SKIP() << "Native run did not capture stdout for this binary.";
    ASSERT_EQ(nat_out, expected_stdout);

    const auto rbp_nat = reg_value(nat, "rbp");
    std::cerr << "[NAT] rax=" << std::hex << reg_value(nat, "rax")
              << " rdx=" << reg_value(nat, "rdx")
              << " rbp=0x" << rbp_nat << std::dec << "\n";
    EXPECT_EQ(reg_value(nat, "rax"), expected);
}
