#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "artifacts/ILibraryScanner.hpp"
#include "artifacts/SummaryWriter.hpp"
#include "core/MemorySegment.hpp"
#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"

using namespace splitter;

namespace {

class FakeScanner : public ILibraryScanner {
public:
    std::vector<LibraryInfo> DetectLibraries(const std::string&) const override {
        LibraryInfo lib;
        lib.SetName("libfake.so");
        lib.SetPath("/tmp/libfake.so");
        lib.SetSoname("libfake.so");
        lib.SetBuildId("abcd");
        return {lib};
    }

    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>&) const override {
        return {{"puts", "libfake.so"}};
    }
};

Partition MakePartition(const std::string& id) {
    Partition p;
    p.SetId(id);
    p.SetStartAddr(0x1000);
    p.SetEndAddr(0x1100);
    p.RawBytes() = {0x01, 0x02};
    p.SetBinHash("binhash");
    p.Inputs() = {"rax"};
    p.Outputs() = {"rbx"};
    p.ExternalCalls() = {"puts"};
    return p;
}

PartitionFiles MakeFiles(const std::string& base) {
    PartitionFiles f;
    f.SetAsmFile(base + ".asm");
    f.SetBinFile(base + ".bin");
    f.SetWrapperFile(base + "_wrapper.c");
    return f;
}

class FakeHash : public IHashAlgorithm {
public:
    void Reset() override { state_ = 0; }
    void AddByte(uint8_t b) override { state_ = (state_ * 1315423911u) ^ b; }
    void AddString(std::string_view s) override {
        for (unsigned char c : s)
            AddByte(c);
    }
    void AddUint64(uint64_t v) override { AddByte(static_cast<uint8_t>(v & 0xff)); }
    void AddBool(bool v) override { AddByte(v ? 1 : 0); }
    std::string Hex() const override { return "fake_" + std::to_string(state_); }
    std::unique_ptr<IHashAlgorithm> Clone() const override { return std::make_unique<FakeHash>(); }

private:
    uint64_t state_ = 0;
};

}  // namespace

TEST(SummaryWriter, WritesSummaryAndHashes) {
    auto scanner = std::make_shared<FakeScanner>();
    auto hash_calc = std::make_shared<SummaryHashCalculator>();
    const std::filesystem::path out_dir = std::filesystem::temp_directory_path() / "splitter_test_out";
    SummaryWriter writer(out_dir, scanner, hash_calc);

    std::vector<Partition> parts;
    parts.push_back(MakePartition("p0"));

    std::vector<PartitionFiles> files;
    files.push_back(MakeFiles("p0"));

    MemorySegment seg;
    seg.SetName(".data");
    seg.SetAddress(0x2000);
    seg.Bytes() = {0xaa, 0xbb};

    std::vector<MemorySegment> mem = {seg};

    writer.Write(parts, files, mem, std::filesystem::path("/bin/ls"));

    std::ifstream in(out_dir / "summary.json");
    ASSERT_TRUE(in.is_open());
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    // Basic presence checks
    EXPECT_NE(content.find("\"schema_version\""), std::string::npos);
    EXPECT_NE(content.find("\"binary\""), std::string::npos);
    EXPECT_NE(content.find("\"binary_os\""), std::string::npos);
    EXPECT_NE(content.find("\"binary_format\""), std::string::npos);
    EXPECT_NE(content.find("\"os\": "), std::string::npos);
    EXPECT_NE(content.find("\"format\": "), std::string::npos);
    EXPECT_NE(content.find("\"partitions\""), std::string::npos);
    EXPECT_NE(content.find("libfake.so"), std::string::npos);
}

TEST(SummaryWriter, AcceptsCustomHashService) {
    auto scanner = std::make_shared<FakeScanner>();
    auto algo = std::make_shared<FakeHash>();
    auto hash_calc = std::make_shared<SummaryHashCalculator>(algo, HashService(algo));
    const std::filesystem::path out_dir =
        std::filesystem::temp_directory_path() / "splitter_test_out_custom";
    SummaryWriter writer(out_dir, scanner, hash_calc);

    std::vector<Partition> parts;
    parts.push_back(MakePartition("p0"));

    std::vector<PartitionFiles> files;
    files.push_back(MakeFiles("p0"));

    MemorySegment seg;
    seg.SetName(".data");
    seg.SetAddress(0x2000);
    seg.Bytes() = {0xaa, 0xbb};
    std::vector<MemorySegment> mem = {seg};

    writer.Write(parts, files, mem, std::filesystem::path("/bin/ls"));
    std::ifstream in(out_dir / "summary.json");
    ASSERT_TRUE(in.is_open());
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    EXPECT_NE(content.find("fake_"), std::string::npos);  // hash issu du FakeHash
}
