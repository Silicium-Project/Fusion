#include <elf.h>
#include <gtest/gtest.h>

#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "core/ExecutionResult.hpp"
#include "core/SegmentLoader.hpp"
#include "support/Logging.hpp"
#include "support/Utils.hpp"

using fragment::ExecutionResult;
using fragment::FdCapture;
using fragment::FdTable;
using fragment::MemoryPatch;
using fragment::SegmentLoader;

namespace {

std::filesystem::path write_binary_file(const std::string& name, const std::vector<uint8_t>& data) {
    auto path = std::filesystem::temp_directory_path() / name;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    return path;
}

std::filesystem::path write_fake_elf(const std::string& name,
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

    return write_binary_file(name, data);
}

}  // namespace

TEST(Utils, Trim) {
    EXPECT_EQ(fragment::trim("  hello \n"), "hello");
    EXPECT_EQ(fragment::trim("\t\r\n"), "");
}

TEST(Utils, AsciiFromUint64) {
    const uint64_t value = 0x4847464544434241ULL;  // "ABCDEFGH" in little-endian
    EXPECT_EQ(fragment::ascii_from_uint64(value), "ABCDEFGH");
}

TEST(Utils, AsciiFromUint64ReplacesNonPrintable) {
    const uint64_t value = 0x0001020304050607ULL;
    EXPECT_EQ(fragment::ascii_from_uint64(value), "........");
}

TEST(Logging, EmitsMessages) {
    std::ostringstream out;
    std::ostringstream err;
    auto* cout_buf = std::cout.rdbuf(out.rdbuf());
    auto* cerr_buf = std::cerr.rdbuf(err.rdbuf());

    fragment::log::banner();
    fragment::log::section("Section");
    fragment::log::subsection("Sub");
    fragment::log::info("info");
    fragment::log::warning("warn");
    fragment::log::error("err");

    std::cout.rdbuf(cout_buf);
    std::cerr.rdbuf(cerr_buf);

    const std::string out_text = out.str();
    const std::string err_text = err.str();

    EXPECT_NE(std::string::npos, out_text.find("Fragment Executor"));
    EXPECT_NE(std::string::npos, out_text.find("[INFO] info"));
    EXPECT_NE(std::string::npos, out_text.find("[WARN] warn"));
    EXPECT_NE(std::string::npos, err_text.find("[ERROR] err"));
}

TEST(FdTable, BasicOperations) {
    FdTable table;
    EXPECT_TRUE(table.empty());
    FdCapture cap;
    cap.data = "abc";
    cap.alias = "stdout";
    table.set(1, cap);
    EXPECT_FALSE(table.empty());
    EXPECT_EQ(table.size(), 1u);
    EXPECT_TRUE(table.contains(1));
    EXPECT_EQ(table.at(1).alias, "stdout");
    table[2].data = "err";
    EXPECT_EQ(table.count(2), 1u);
}

TEST(ExecutionResult, PrintSuccessAndError) {
    ExecutionResult result;
    result.success = true;
    result.instructions_executed = 7;
    result.memory_accesses = 3;
    result.initial_regs = {{"rax", 1}};
    result.final_regs = {{"rax", 2}};
    result.program_stdout = "OUT\n";
    result.program_stderr = "ERR";
    MemoryPatch patch;
    patch.address = 0x1000;
    patch.before = {0x00};
    patch.after = {0x01};
    result.memory_patches.push_back(patch);
    FdCapture cap;
    cap.data = "fd";
    result.fd_outputs.set(3, cap);

    std::ostringstream out;
    std::ostringstream err;
    auto* cout_buf = std::cout.rdbuf(out.rdbuf());
    auto* cerr_buf = std::cerr.rdbuf(err.rdbuf());

    result.print();

    ExecutionResult error_result;
    error_result.success = false;
    error_result.error_message = "boom";
    error_result.print();

    std::cout.rdbuf(cout_buf);
    std::cerr.rdbuf(cerr_buf);

    const std::string out_text = out.str();
    const std::string err_text = err.str();

    EXPECT_NE(std::string::npos, out_text.find("Instructions"));
    EXPECT_NE(std::string::npos, out_text.find("OUT"));
    EXPECT_NE(std::string::npos, out_text.find("ERR"));
    EXPECT_NE(std::string::npos, err_text.find("[ERROR]"));
}

TEST(ExecutionResult, PrintAddsNewlinesAndListsFdOutputs) {
    ExecutionResult result;
    result.success = true;
    result.instructions_executed = 1;
    result.memory_accesses = 1;
    result.program_stdout = "OK";
    result.program_stderr = "WARN";
    FdCapture cap;
    cap.data = "data";
    cap.alias = "stdout";
    result.fd_outputs.set(1, cap);

    std::ostringstream out;
    std::ostringstream err;
    auto* cout_buf = std::cout.rdbuf(out.rdbuf());
    auto* cerr_buf = std::cerr.rdbuf(err.rdbuf());

    result.print();

    std::cout.rdbuf(cout_buf);
    std::cerr.rdbuf(cerr_buf);

    const std::string out_text = out.str();
    EXPECT_NE(std::string::npos, out_text.find("OK\n"));
    EXPECT_NE(std::string::npos, out_text.find("WARN\n"));
    EXPECT_NE(std::string::npos, out_text.find("FDs captur"));
}

TEST(SegmentLoader, ReadsStringsAndBytes) {
    const uint64_t vaddr = 0x400000;
    const std::string text = "hello";
    std::vector<uint8_t> payload(text.begin(), text.end());
    payload.push_back('\0');
    auto path = write_fake_elf("segment_loader_test.bin", vaddr, payload);

    SegmentLoader loader(path.string());
    auto str = loader.read_string(vaddr);
    ASSERT_TRUE(str.has_value());
    EXPECT_EQ(str.value(), "hello");

    auto bytes = loader.read_bytes(vaddr, 5);
    ASSERT_EQ(bytes.size(), 5u);
    EXPECT_EQ(std::string(bytes.begin(), bytes.end()), "hello");

    auto zero = loader.read_bytes(vaddr, 0);
    EXPECT_TRUE(zero.empty());

    auto empty = loader.read_bytes(vaddr + 0x1000, 4);
    EXPECT_TRUE(empty.empty());
}

TEST(SegmentLoader, RejectsInvalidBinary) {
    const std::vector<uint8_t> data = {'b', 'a', 'd'};
    auto path = write_binary_file("segment_loader_bad.bin", data);
    SegmentLoader loader(path.string());
    EXPECT_FALSE(loader.read_string(0x1000).has_value());
}

TEST(SegmentLoader, RejectsEmptyPath) {
    SegmentLoader loader("");
    EXPECT_FALSE(loader.read_string(0x10).has_value());
    EXPECT_TRUE(loader.read_bytes(0x10, 4).empty());
}
