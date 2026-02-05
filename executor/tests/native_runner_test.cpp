#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <vector>

#include "runtime/NativeRunner.hpp"
#include "core/FragmentExecutor.hpp"

using fragment::ExecutionEntry;
using fragment::ExecutionResult;
using fragment::FragmentExecutor;
using fragment::NativeRunner;
using fragment::PartitionInfo;

namespace {

std::string write_temp_bin(const std::vector<uint8_t>& bytes, const std::string& name) {
    auto path = std::filesystem::temp_directory_path() / name;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    return path.string();
}

ExecutionEntry make_entry(const PartitionInfo& info) {
    ExecutionEntry entry;
    entry.name = info.id;
    entry.asm_path = info.asm_path;
    entry.meta = std::cref(info);
    return entry;
}

}  // namespace

#ifdef __linux__

TEST(NativeRunner, RunsSimpleRet) {
    const std::string bin_path = write_temp_bin({0xC3}, "native_runner_ret.bin");

    PartitionInfo info;
    info.id = "p0";
    info.asm_path = "p0.asm";
    info.bin_path = bin_path;
    info.start_address = 0x1000;
    info.binary_size = 1;

    FragmentExecutor executor;
    ExecutionResult result;
    NativeRunner runner(false);

    ASSERT_TRUE(runner.run(make_entry(info), executor, result));
    EXPECT_TRUE(result.success);
    EXPECT_TRUE(result.error_message.empty());
}

TEST(NativeRunner, BlocksMissingSymbolsWithoutForce) {
    const std::string bin_path = write_temp_bin({0xC3}, "native_runner_missing.bin");

    PartitionInfo info;
    info.id = "p_missing";
    info.asm_path = "p_missing.asm";
    info.bin_path = bin_path;
    info.start_address = 0x2000;
    info.binary_size = 1;
    info.unresolved_calls.push_back("401000 <missing_symbol@plt>");

    FragmentExecutor executor;
    ExecutionResult result;
    NativeRunner runner(false);

    EXPECT_FALSE(runner.run(make_entry(info), executor, result));
    EXPECT_FALSE(result.success);
    EXPECT_NE(result.error_message.find("missing_symbol"), std::string::npos);
}

#else

TEST(NativeRunner, UnsupportedOnNonLinux) {
    GTEST_SKIP() << "Native runner tests are Linux-only.";
}

#endif