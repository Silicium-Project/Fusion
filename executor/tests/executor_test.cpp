#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <cstring>
#include <unistd.h>

#include <gtest/gtest.h>

#include "core/Config.hpp"
#include "core/FragmentExecutor.hpp"

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

TEST(FragmentExecutor, MovUpdatesMemoryAndPushHandlesMemoryOperands) {
    const std::string asm_path = write_temp_asm(
        "0000000000002000: push rax\n"
        "0000000000002008: mov QWORD PTR [rsp], rbx\n"
        "0000000000002010: pop rcx\n"
        "0000000000002018: ret\n",
        "fragment_executor_memory.asm");

    FragmentExecutor executor;
    executor.set_input("rax", 0);
    executor.set_input("rbx", 0x42);

    auto result = executor.execute_safe(asm_path);

    ASSERT_TRUE(result.success);
    ASSERT_TRUE(result.final_regs.count("rcx"));
    EXPECT_EQ(result.final_regs.at("rcx"), 0x42u);
    EXPECT_FALSE(result.memory_patches.empty());
}

TEST(FragmentExecutor, CaptureProgramStdout) {
    ExecutorConfig cfg;
    cfg.fd_rules.push_back(fragment::FdRule{STDOUT_FILENO, {}, true, "stdout"});
    FragmentExecutor executor(cfg);

    const std::string captured = executor.capture_program_stdout([] {
        std::cout << "hello-out";
        std::cerr << "hello-err";
    });

    EXPECT_EQ(captured, "hello-out");
}

TEST(FragmentExecutor, CaptureStdoutAndStderr) {
    FragmentExecutor executor;

    auto pipes = executor.capture_program_pipes([] {
        std::cout << "out-stream";
        std::cerr << "err-stream";
    });

    EXPECT_EQ(pipes.fds[STDOUT_FILENO].data, "out-stream");
    EXPECT_EQ(pipes.fds[STDERR_FILENO].data, "err-stream");
}

TEST(FragmentExecutor, InjectStdinAndCaptureOutput) {
    ExecutorConfig cfg;
    cfg.fd_rules.push_back(fragment::FdRule{STDIN_FILENO, "hello-in\n", false, "stdin"});
    cfg.fd_rules.push_back(fragment::FdRule{STDOUT_FILENO, {}, true, "stdout"});
    cfg.fd_rules.push_back(fragment::FdRule{STDERR_FILENO, {}, true, "stderr"});
    FragmentExecutor executor(cfg);

    auto pipes = executor.capture_program_pipes([] {
        std::string line;
        std::getline(std::cin, line);
        std::cout << line;
        std::cerr << line;
    });

    EXPECT_EQ(pipes.fds[STDOUT_FILENO].data, "hello-in");
    EXPECT_EQ(pipes.fds[STDERR_FILENO].data, "hello-in");
}

TEST(FragmentExecutor, CaptureAndFeedExtraFd) {
    ExecutorConfig cfg;
    fragment::FdRule cap{};
    cap.fd = 3;
    cap.capture = true;
    cfg.fd_rules.push_back(cap);

    FragmentExecutor executor(cfg);
    auto pipes = executor.capture_program_pipes([] {
        ::write(3, "hey there", 9);
    });

    ASSERT_TRUE(pipes.fds.count(3));
    EXPECT_EQ(pipes.fds[3].data, "hey there");
}
