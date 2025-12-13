#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "worker/queue_loader.hpp"

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
}
