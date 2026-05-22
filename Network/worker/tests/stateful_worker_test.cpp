#include <filesystem>
#include <fstream>
#include <sstream>

#include <gtest/gtest.h>

#include "worker/core/Worker.hpp"

namespace {

std::string write_fragment(const std::string& name, std::string_view content) {
    auto dir = std::filesystem::temp_directory_path() / "worker_state_tests";
    std::filesystem::create_directories(dir);
    auto path = dir / name;
    std::ofstream out(path);
    out << content;
    return path.string();
}

std::string make_partition_json(const std::string& id,
                                const std::string& asm_path,
                                uint64_t start_addr) {
    std::ostringstream oss;
    oss << "{"
        << "\"id\":\"" << id << "\","
        << "\"asm\":\"" << asm_path << "\","
        << "\"bin\":\"\","
        << "\"wrapper\":\"\","
        << "\"bin_hash\":\"\","
        << "\"partition_hash\":\"\","
        << "\"start\":\"0x" << std::hex << start_addr << std::dec << "\","
        << "\"end\":null,"
        << "\"size\":0,"
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
        << "}";
    return oss.str();
}

std::string write_summary(const std::string& writer_path, const std::string& reader_path) {
    auto dir = std::filesystem::temp_directory_path() / "worker_state_tests";
    std::filesystem::create_directories(dir);
    auto path = dir / "summary.json";
    std::ofstream out(path);
    out << "{"
        << "\"binary\":\"\","
        << "\"binary_hash\":\"\","
        << "\"memory_hash\":\"\","
        << "\"summary_hash\":\"\","
        << "\"can_split\":true,"
        << "\"required_libraries\":[],"
        << "\"libraries\":[],"
        << "\"partitions\":["
        << make_partition_json("writer", writer_path, 0x1000) << ","
        << make_partition_json("reader", reader_path, 0x2000)
        << "],"
        << "\"initial_memory\":[]"
        << "}";
    return path.string();
}

fragment::PartitionInfo make_partition(const std::string& id,
                                       const std::string& asm_path,
                                       uint64_t start_addr = 0) {
    fragment::PartitionInfo info;
    info.id = id;
    info.asm_path = asm_path;
    if (start_addr)
        info.start_address = start_addr;
    return info;
}

}  // namespace

TEST(StatefulWorker, MemoryWritesAreVisibleAcrossFragments) {
    const std::string writer_path = write_fragment(
        "writer.asm",
        "0000000000001000: mov rax, $0x12345678\n"
        "0000000000001008: push rax\n"
        "0000000000001010: ret\n");

    const std::string reader_path = write_fragment(
        "reader.asm",
        "0000000000002000: pop rbx\n"
        "0000000000002008: ret\n");

    const std::string summary_path = write_summary(writer_path, reader_path);

    fragment::PartitionInfo writer = make_partition("writer", writer_path, 0x1000);
    fragment::PartitionInfo reader = make_partition("reader", reader_path, 0x2000);

    worker::WorkerConfig config;
    config.mode = worker::ExecutionMode::Emulator;
    config.dynamo_runner_binary.clear();
    config.emulator_library = (std::filesystem::path("..") / "executor" / "libfragment_emulator.so").lexically_normal().string();
    worker::Worker worker(config);

    worker::Task writer_task;
    writer_task.partition_id = "writer";

    auto writer_report = worker.run_task(writer, writer_path, "", summary_path, writer_task);
    ASSERT_TRUE(writer_report.result.success);

    worker::Task reader_task;
    reader_task.partition_id = "reader";

    auto reader_report = worker.run_task(reader, reader_path, "", summary_path, reader_task);
    ASSERT_TRUE(reader_report.result.success);
    ASSERT_TRUE(reader_report.result.final_regs.count("rbx"));
    EXPECT_EQ(reader_report.result.final_regs.at("rbx"), 0x12345678u);
}
