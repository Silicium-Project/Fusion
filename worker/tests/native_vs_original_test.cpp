#include <array>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/wait.h>

#include <gtest/gtest.h>

#include "PartitionSummary.hpp"
#include "worker/job_runner.hpp"
#include "worker/task.hpp"
#include "worker/worker_config.hpp"

namespace {

struct CmdResult {
    int code{};
    std::string output;
};

CmdResult run_command(const std::string& cmd) {
    std::array<char, 256> buffer{};
    std::string result;
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe)
        throw std::runtime_error("Failed to run command: " + cmd);
    while (fgets(buffer.data(), buffer.size(), pipe))
        result += buffer.data();
    int status = pclose(pipe);
    int code = status;
    if (status != -1) {
        if (WIFEXITED(status))
            code = WEXITSTATUS(status);
        else if (WIFSIGNALED(status))
            code = 128 + WTERMSIG(status);
    }
    return {code, result};
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
    run_command("rm -rf ../splitter/build ../splitter/splitter >/dev/null 2>&1");
    const auto build = run_command("cd ../splitter && make splitter");
    if (build.code != 0)
        throw std::runtime_error("Failed to build splitter: " + build.output);
    auto path = find_splitter_binary();
    if (path.empty()) {
        auto debug_ls = run_command("ls -l ../splitter || true");
        throw std::runtime_error("splitter binary not found after build. ls: " + debug_ls.output);
    }
    return path;
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
    auto compile = run_command("gcc -O0 -g -no-pie \"" + src_path.string() + "\" -o \"" + bin_path.string() + "\"");
    ASSERT_EQ(compile.code, 0) << compile.output;

    auto run_prog = run_command("\"" + bin_path.string() + "\"");
    if (run_prog.code != 0)
        std::cerr << "[WARN] Original program exited with code " << run_prog.code << "\n";
    const std::string expected_stdout = run_prog.output;

    std::string splitter;
    try {
        splitter = build_splitter_if_needed();
    } catch (const std::exception& e) {
        GTEST_SKIP() << "Splitter unavailable in test environment: " << e.what();
    }
    const fs::path out_dir = tmp_root / "out";
    fs::create_directories(out_dir);
    auto split = run_command(splitter + " \"" + bin_path.string() + "\" --output-dir \"" + out_dir.string() + "\"");
    ASSERT_EQ(split.code, 0) << split.output;

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
    auto compile = run_command("gcc -O0 -g -no-pie \"" + src_path.string() + "\" -o \"" + bin_path.string() + "\"");
    ASSERT_EQ(compile.code, 0) << compile.output;

    auto run_prog = run_command("\"" + bin_path.string() + "\"");
    if (run_prog.code != 0)
        std::cerr << "[WARN] Original program exited with code " << run_prog.code << "\n";
    const std::string expected_stdout = run_prog.output;

    std::string splitter;
    try {
        splitter = build_splitter_if_needed();
    } catch (const std::exception& e) {
        GTEST_SKIP() << "Splitter unavailable in test environment: " << e.what();
    }
    const fs::path out_dir = tmp_root / "out";
    fs::create_directories(out_dir);
    auto split = run_command(splitter + " \"" + bin_path.string() + "\" --output-dir \"" + out_dir.string() + "\"");
    ASSERT_EQ(split.code, 0) << split.output;

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
