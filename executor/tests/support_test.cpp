#include <elf.h>
#include <gtest/gtest.h>

#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
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

std::filesystem::path write_fake_pe(const std::string& name,
                                    uint64_t image_base,
                                    uint32_t section_rva,
                                    const std::vector<uint8_t>& payload,
                                    bool with_import_table = false) {
    std::vector<uint8_t> data(0x200 + payload.size(), 0);

    data[0] = 'M';
    data[1] = 'Z';
    const uint32_t pe_offset = 0x80;
    std::memcpy(data.data() + 0x3c, &pe_offset, sizeof(pe_offset));
    data[pe_offset + 0] = 'P';
    data[pe_offset + 1] = 'E';

    const uint32_t file_header = pe_offset + 4;
    const uint16_t machine = 0x8664;  // AMD64
    const uint16_t number_of_sections = 1;
    const uint16_t optional_header_size = 0xF0;
    const uint16_t characteristics = 0x0022;
    std::memcpy(data.data() + file_header + 0, &machine, sizeof(machine));
    std::memcpy(data.data() + file_header + 2, &number_of_sections, sizeof(number_of_sections));
    std::memcpy(data.data() + file_header + 16, &optional_header_size, sizeof(optional_header_size));
    std::memcpy(data.data() + file_header + 18, &characteristics, sizeof(characteristics));

    const uint32_t optional = file_header + 20;
    const uint16_t magic = 0x20b;  // PE32+
    const uint32_t entrypoint_rva = section_rva;
    const uint32_t section_alignment = 0x1000;
    const uint32_t file_alignment = 0x200;
    const uint32_t size_of_image = 0x2000;
    const uint32_t size_of_headers = 0x200;
    const uint32_t number_of_rva_and_sizes = 16;
    std::memcpy(data.data() + optional + 0, &magic, sizeof(magic));
    std::memcpy(data.data() + optional + 16, &entrypoint_rva, sizeof(entrypoint_rva));
    std::memcpy(data.data() + optional + 24, &image_base, sizeof(image_base));
    std::memcpy(data.data() + optional + 32, &section_alignment, sizeof(section_alignment));
    std::memcpy(data.data() + optional + 36, &file_alignment, sizeof(file_alignment));
    std::memcpy(data.data() + optional + 56, &size_of_image, sizeof(size_of_image));
    std::memcpy(data.data() + optional + 60, &size_of_headers, sizeof(size_of_headers));
    std::memcpy(data.data() + optional + 108, &number_of_rva_and_sizes, sizeof(number_of_rva_and_sizes));

    if (with_import_table) {
        const uint32_t import_rva = 0x1800;
        const uint32_t import_size = 0x40;
        std::memcpy(data.data() + optional + 120, &import_rva, sizeof(import_rva));
        std::memcpy(data.data() + optional + 124, &import_size, sizeof(import_size));
    }

    const uint32_t section_header = optional + optional_header_size;
    const char section_name[8] = {'.', 'r', 'd', 'a', 't', 'a', 0, 0};
    const uint32_t virtual_size = static_cast<uint32_t>(payload.size());
    const uint32_t size_of_raw_data = static_cast<uint32_t>(payload.size());
    const uint32_t pointer_to_raw_data = 0x200;
    const uint32_t characteristics_section = 0x40000040;  // read + initialized data
    std::memcpy(data.data() + section_header + 0, section_name, sizeof(section_name));
    std::memcpy(data.data() + section_header + 8, &virtual_size, sizeof(virtual_size));
    std::memcpy(data.data() + section_header + 12, &section_rva, sizeof(section_rva));
    std::memcpy(data.data() + section_header + 16, &size_of_raw_data, sizeof(size_of_raw_data));
    std::memcpy(data.data() + section_header + 20, &pointer_to_raw_data, sizeof(pointer_to_raw_data));
    std::memcpy(data.data() + section_header + 36, &characteristics_section, sizeof(characteristics_section));

    std::memcpy(data.data() + pointer_to_raw_data, payload.data(), payload.size());
    return write_binary_file(name, data);
}

std::filesystem::path find_pe_fixture(const std::string& filename) {
    std::vector<std::filesystem::path> starts = {
        std::filesystem::current_path(),
        std::filesystem::path(__FILE__).parent_path()
    };

    for (const auto& start : starts) {
        std::filesystem::path probe = std::filesystem::absolute(start);
        while (!probe.empty()) {
            const auto candidate = probe / "tests" / "fixtures" / "pe" / filename;
            if (std::filesystem::exists(candidate))
                return candidate;
            const auto parent = probe.parent_path();
            if (parent == probe)
                break;
            probe = parent;
        }
    }

    throw std::runtime_error("PE fixture not found: " + filename);
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

TEST(SegmentLoader, ReadsPeStringsAndEntrypoint) {
    const uint64_t image_base = 0x140000000ULL;
    const uint32_t rva = 0x1000;
    std::vector<uint8_t> payload = {'h', 'e', 'l', 'l', 'o', 0};
    auto path = write_fake_pe("segment_loader_pe.bin", image_base, rva, payload);

    SegmentLoader loader(path.string());
    auto str = loader.read_string(image_base + rva);
    ASSERT_TRUE(str.has_value());
    EXPECT_EQ(*str, "hello");
    EXPECT_EQ(loader.format(), SegmentLoader::BinaryFormat::Pe32Plus);
    ASSERT_TRUE(loader.entrypoint().has_value());
    EXPECT_EQ(*loader.entrypoint(), image_base + rva);
}

TEST(SegmentLoader, RejectsPeWithImportTable) {
    const uint64_t image_base = 0x140000000ULL;
    const uint32_t rva = 0x1000;
    std::vector<uint8_t> payload = {'x', 0};
    auto path = write_fake_pe("segment_loader_pe_imports.bin", image_base, rva, payload, true);

    SegmentLoader loader(path.string());
    EXPECT_FALSE(loader.read_string(image_base + rva).has_value());
    EXPECT_NE(loader.last_error().find("import table"), std::string::npos);
}

TEST(SegmentLoader, UsesVersionedPeFixtureCorpus) {
    const uint64_t image_base = 0x140000000ULL;
    const uint32_t rva = 0x1000;

    SegmentLoader valid_loader(find_pe_fixture("valid-minimal-pe64.exe").string());
    ASSERT_TRUE(valid_loader.entrypoint().has_value());
    EXPECT_EQ(*valid_loader.entrypoint(), image_base + rva);
    auto valid_string = valid_loader.read_string(image_base + rva);
    ASSERT_TRUE(valid_string.has_value());
    EXPECT_EQ(*valid_string, "fixture-ok");
    EXPECT_EQ(valid_loader.format(), SegmentLoader::BinaryFormat::Pe32Plus);

    SegmentLoader malformed_loader(find_pe_fixture("malformed-mz-only.exe").string());
    EXPECT_FALSE(malformed_loader.read_string(image_base + rva).has_value());
    EXPECT_EQ(malformed_loader.format(), SegmentLoader::BinaryFormat::Unknown);

    SegmentLoader unsupported_loader(find_pe_fixture("unsupported-import-table-pe64.exe").string());
    EXPECT_FALSE(unsupported_loader.read_string(image_base + rva).has_value());
    EXPECT_NE(unsupported_loader.last_error().find("import table"), std::string::npos);
}
