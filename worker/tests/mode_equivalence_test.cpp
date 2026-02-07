#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>

#include <gtest/gtest.h>

#include "worker/runtime/JobRunner.hpp"
#include "worker/task/Task.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace {

std::string write_file(const std::filesystem::path& path, const std::vector<uint8_t>& bytes) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::out | std::ios::trunc);
    for (auto b : bytes)
        out.put(static_cast<char>(b));
    return path.string();
}

std::string write_text(const std::filesystem::path& path, const std::string& content) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::out | std::ios::trunc);
    out << content;
    return path.string();
}

std::string make_summary_json(const std::string& asm_path,
                              const std::string& bin_path,
                              size_t bin_size,
                              uint64_t start_addr) {
    std::ostringstream oss;
    oss << "{"
        << "\"binary\":\"\","
        << "\"binary_hash\":\"\","
        << "\"memory_hash\":\"\","
        << "\"summary_hash\":\"\","
        << "\"can_split\":true,"
        << "\"required_libraries\":[],"
        << "\"libraries\":[],"
        << "\"partitions\":[{"
        << "\"id\":\"p1\","
        << "\"asm\":\"" << asm_path << "\","
        << "\"bin\":\"" << bin_path << "\","
        << "\"wrapper\":\"\","
        << "\"bin_hash\":\"\","
        << "\"partition_hash\":\"\","
        << "\"start\":\"0x" << std::hex << start_addr << std::dec << "\","
        << "\"end\":null,"
        << "\"size\":" << bin_size << ","
        << "\"parallelizable\":false,"
        << "\"requires_display\":false,"
        << "\"parents\":[],"
        << "\"dependencies\":[],"
        << "\"unresolved_calls\":[],"
        << "\"inputs\":[],"
        << "\"external_inputs\":[],"
        << "\"outputs\":[],"
        << "\"external_calls\":[],"
        << "\"required_libraries\":[]"
        << "}],"
        << "\"initial_memory\":[]"
        << "}";
    return oss.str();
}

worker::WorkerConfig make_config(worker::ExecutionMode mode) {
    worker::WorkerConfig cfg;
    cfg.mode = mode;
    cfg.emulator_library = (std::filesystem::path("..") / "executor" / "libfragment_emulator.so").lexically_normal().string();
    cfg.native_library = (std::filesystem::path("..") / "executor" / "libfragment_executor.so").lexically_normal().string();
    cfg.dynamo_runner_binary.clear();
    return cfg;
}

}  // namespace

TEST(WorkerModeEquivalence, EmulatorAndNativeYieldSameRegisters) {
    // Génère un fragment simple: mov rax, 2; add rax, 3; ret
    const std::filesystem::path tmp_root = std::filesystem::temp_directory_path() / "worker_mode_eq";
    const auto asm_path = write_text(tmp_root / "p1.asm",
                                     "0000000000001000: mov rax, $0x2\n"
                                     "000000000000100A: add rax, $0x3\n"
                                     "0000000000001010: ret\n");
    const std::vector<uint8_t> bin_bytes = {
        0x48, 0xB8, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  // mov rax, 0x2
        0x48, 0x05, 0x03, 0x00, 0x00, 0x00,                          // add rax, 0x3
        0xC3                                                         // ret
    };
    const auto bin_path = write_file(tmp_root / "p1.bin", bin_bytes);
    const auto summary_path = write_text(tmp_root / "summary.json",
                                         make_summary_json(asm_path, bin_path, bin_bytes.size(), 0x1000));

    // On désactive les vérifications de hash pour ce test synthétique.
    setenv("SKIP_HASH", "1", 1);

    worker::Task task;
    task.partition_id = "p1";

    worker::JobRunner emu_runner(summary_path, make_config(worker::ExecutionMode::Emulator));
    auto emu_report = emu_runner.execute(task);
    ASSERT_TRUE(emu_report.result.success);
    ASSERT_TRUE(emu_report.result.final_regs.count("rax"));
    EXPECT_EQ(emu_report.result.final_regs.at("rax"), 5u);

    worker::JobRunner native_runner(summary_path, make_config(worker::ExecutionMode::Native));
    auto nat_report = native_runner.execute(task);
    ASSERT_TRUE(nat_report.result.success);
    ASSERT_TRUE(nat_report.result.final_regs.count("rax"));
    EXPECT_EQ(nat_report.result.final_regs.at("rax"), 5u);

    // Vérifie l'équivalence émulation vs natif sur le registre final.
    EXPECT_EQ(emu_report.result.final_regs.at("rax"), nat_report.result.final_regs.at("rax"));
}
