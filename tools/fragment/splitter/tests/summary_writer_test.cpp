#include <gtest/gtest.h>

#include <fstream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "splitter/artifacts/ILibraryScanner.hpp"
#include "splitter/artifacts/SummaryWriter.hpp"
#include "splitter/core/MemorySegment.hpp"
#include "splitter/core/Partition.hpp"
#include "splitter/core/PartitionFiles.hpp"

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

}  // namespace

TEST(SummaryWriter, WritesSummaryAndHashes) {
    auto scanner = std::make_shared<FakeScanner>();
    SummaryWriter writer("/tmp/splitter_test_out", scanner);

    std::vector<Partition> parts;
    parts.push_back(MakePartition("p0"));

    std::vector<PartitionFiles> files;
    files.push_back(MakeFiles("p0"));

    MemorySegment seg;
    seg.SetName(".data");
    seg.SetAddress(0x2000);
    seg.Bytes() = {0xaa, 0xbb};

    std::vector<MemorySegment> mem = {seg};

    writer.Write(parts, files, mem, "/bin/ls");

    std::ifstream in("/tmp/splitter_test_out/summary.json");
    ASSERT_TRUE(in.is_open());
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    // Basic presence checks
    EXPECT_NE(content.find("\"binary\""), std::string::npos);
    EXPECT_NE(content.find("\"partitions\""), std::string::npos);
    EXPECT_NE(content.find("libfake.so"), std::string::npos);
}
