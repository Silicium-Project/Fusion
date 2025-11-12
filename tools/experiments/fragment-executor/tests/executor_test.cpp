#include <filesystem>
#include <fstream>
#include <string>

#include <gtest/gtest.h>

#include "fragment/config.hpp"
#include "fragment/fragment_executor.hpp"

using fragment::ExecutorConfig;
using fragment::FragmentExecutor;

static std::string write_temp_asm(const std::string& content, const std::string& name) {
    auto path = std::filesystem::temp_directory_path() / name;
    std::ofstream out(path);
    out << content;
    return path.string();
}

TEST(FragmentExecutor, ExecuteSafeSimpleProgram) {
    const std::string asm_path = write_temp_asm(
        "0000000000001000: mov rax, rbx\n"
        "0000000000001008: add rax, rcx\n"
        "0000000000001010: ret\n",
        "fragment_executor_basic.asm");

    FragmentExecutor executor;
    executor.set_input("rbx", 2);
    executor.set_input("rcx", 3);

    auto result = executor.execute_safe(asm_path);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(executor.get_register("rax"), 5u);
    EXPECT_EQ(result.instructions_executed, 3u);
}

