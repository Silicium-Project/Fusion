#include <elf.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>
#include <cstring>
#include <unistd.h>
#include <vector>

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

static std::filesystem::path write_fake_elf(const std::string& name,
                                            uint64_t vaddr,
                                            const std::vector<uint8_t>& payload) {
    Elf64_Ehdr header{};
    std::memcpy(header.e_ident, ELFMAG, SELFMAG);
    header.e_ident[EI_CLASS] = ELFCLASS64;
    header.e_ident[EI_DATA] = ELFDATA2LSB;
    header.e_ident[EI_VERSION] = EV_CURRENT;
    header.e_ident[EI_OSABI] = ELFOSABI_SYSV;
    header.e_type = ET_EXEC;
    header.e_machine = EM_X86_64;
    header.e_version = EV_CURRENT;
    header.e_phoff = sizeof(Elf64_Ehdr);
    header.e_ehsize = sizeof(Elf64_Ehdr);
    header.e_phentsize = sizeof(Elf64_Phdr);
    header.e_phnum = 1;

    Elf64_Phdr phdr{};
    phdr.p_type = PT_LOAD;
    phdr.p_offset = 0x100;
    phdr.p_vaddr = vaddr;
    phdr.p_paddr = vaddr;
    phdr.p_filesz = payload.size();
    phdr.p_memsz = payload.size();
    phdr.p_flags = PF_R;

    std::vector<uint8_t> data;
    const size_t total_size = static_cast<size_t>(phdr.p_offset + payload.size());
    data.resize(total_size, 0);
    std::memcpy(data.data(), &header, sizeof(header));
    std::memcpy(data.data() + sizeof(header), &phdr, sizeof(phdr));
    std::memcpy(data.data() + phdr.p_offset, payload.data(), payload.size());

    auto path = std::filesystem::temp_directory_path() / name;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    return path;
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

TEST(FragmentExecutor, EmulateCallPutsUsesEmulatorMemory) {
    FragmentExecutor executor;
    const uint64_t addr = 0x8000;
    executor.apply_memory_bytes(addr, {'h', 'i', 0});
    executor.set_input("rdi", addr);

    const std::string asm_path = write_temp_asm(
        "0000000000001000: call puts\n",
        "fragment_executor_puts_mem.asm");

    auto result = executor.execute_safe(asm_path);
    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.program_stdout, "hi\n");
    EXPECT_EQ(executor.get_register("rax"), 2u);
}

TEST(FragmentExecutor, EmulateCallPutsUsesBinaryString) {
    const uint64_t vaddr = 0x600000;
    std::vector<uint8_t> payload{'h','e','l','l','o','\0'};
    auto bin = write_fake_elf("fragment_executor_puts.bin", vaddr, payload);

    ExecutorConfig cfg;
    cfg.binary_path = bin.string();
    FragmentExecutor executor(cfg);
    executor.set_input("rdi", vaddr);

    const std::string asm_path = write_temp_asm(
        "0000000000001000: call puts\n",
        "fragment_executor_puts.asm");

    auto result = executor.execute_safe(asm_path);
    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.program_stdout, "hello\n");
    EXPECT_EQ(executor.get_register("rax"), 5u);
}

TEST(FragmentExecutor, EmulateCallPrintfFormatsArgs) {
    const uint64_t vaddr = 0x700000;
    const std::string fmt = "value=%d";
    std::vector<uint8_t> payload(fmt.begin(), fmt.end());
    payload.push_back('\0');
    auto bin = write_fake_elf("fragment_executor_printf.bin", vaddr, payload);

    ExecutorConfig cfg;
    cfg.binary_path = bin.string();
    FragmentExecutor executor(cfg);
    executor.set_input("rdi", vaddr);
    executor.set_input("rsi", 42);

    const std::string asm_path = write_temp_asm(
        "0000000000002000: call printf\n",
        "fragment_executor_printf.asm");

    auto result = executor.execute_safe(asm_path);
    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.program_stdout, "value=42");
}

TEST(FragmentExecutor, ExecuteNativeNoopReturnsSuccess) {
    FragmentExecutor executor;
    std::vector<uint8_t> empty;
    auto result = executor.execute_native(empty, std::nullopt);
    EXPECT_TRUE(result.success);
}
