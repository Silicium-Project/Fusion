#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "worker/io/QueueLoader.hpp"

namespace {

std::filesystem::path write_queue_file(std::string_view content) {
    auto path = std::filesystem::temp_directory_path() / "worker_queue_test.txt";
    std::ofstream out(path);
    out << content;
    return path;
}

}  // namespace

TEST(QueueLoader, ParsesSimpleFile) {
    const auto path = write_queue_file(R"(# demo
func_0_deregister_tm_clones
func_3_main rax=0x10 rbx=42
)");

    auto tasks = worker::load_queue_file(path.string());
    ASSERT_EQ(tasks.size(), 2u);
    EXPECT_EQ(tasks[0].partition_id, "func_0_deregister_tm_clones");
    EXPECT_TRUE(tasks[0].inputs.empty());

    EXPECT_EQ(tasks[1].partition_id, "func_3_main");
    ASSERT_EQ(tasks[1].inputs.size(), 2u);
    EXPECT_EQ(tasks[1].inputs.at("rax"), 0x10u);
    EXPECT_EQ(tasks[1].inputs.at("rbx"), 42u);
    EXPECT_EQ(tasks[1].type, worker::TaskType::Binary);
}

TEST(QueueLoader, ParsesHexAndDecimal) {
    EXPECT_EQ(worker::parse_register_value("0x10"), 16u);
    EXPECT_EQ(worker::parse_register_value("123"), 123u);
}

TEST(QueueLoader, InvalidTokensThrow) {
    EXPECT_THROW(worker::parse_register_value(""), std::runtime_error);
    EXPECT_THROW(worker::parse_register_value("abc"), std::exception);

    const auto path = write_queue_file("func_1 rax-\n");
    EXPECT_THROW(worker::load_queue_file(path.string()), std::runtime_error);

    const auto bad_type = write_queue_file("func_2 type=unknown\n");
    EXPECT_THROW(worker::load_queue_file(bad_type.string()), std::runtime_error);
}

TEST(QueueLoader, SkipsBlankAndComments) {
    const auto path = write_queue_file(R"(
# comment

task1 type=binary rax=1
task2 type=health
)");
    auto tasks = worker::load_queue_file(path.string());
    ASSERT_EQ(2u, tasks.size());
    EXPECT_EQ("task1", tasks[0].partition_id);
    EXPECT_EQ(1u, tasks[0].inputs.at("rax"));
    EXPECT_EQ(tasks[0].type, worker::TaskType::Binary);
    EXPECT_EQ("task2", tasks[1].partition_id);
    EXPECT_TRUE(tasks[1].inputs.empty());
    EXPECT_EQ(tasks[1].type, worker::TaskType::Health);
}

TEST(QueueLoader, MissingFileThrows) {
    EXPECT_THROW(worker::load_queue_file("/tmp/definitely_missing_queue.txt"), std::runtime_error);
}
