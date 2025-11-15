#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "worker/worker.hpp"

namespace {

std::string write_fragment(const std::string& name, std::string_view content) {
    auto dir = std::filesystem::temp_directory_path() / "worker_state_tests";
    std::filesystem::create_directories(dir);
    auto path = dir / name;
    std::ofstream out(path);
    out << content;
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

    fragment::PartitionInfo writer = make_partition("writer", writer_path, 0x1000);
    fragment::PartitionInfo reader = make_partition("reader", reader_path, 0x2000);

    worker::WorkerConfig config;
    worker::Worker worker(config);

    worker::Task writer_task;
    writer_task.partition_id = "writer";

    auto writer_report = worker.run_task(writer, writer_path, "", writer_task);
    ASSERT_TRUE(writer_report.result.success);

    worker::Task reader_task;
    reader_task.partition_id = "reader";

    auto reader_report = worker.run_task(reader, reader_path, "", reader_task);
    ASSERT_TRUE(reader_report.result.success);
    ASSERT_TRUE(reader_report.result.final_regs.count("rbx"));
    EXPECT_EQ(reader_report.result.final_regs.at("rbx"), 0x12345678u);
}
