#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "api/FragmentApi.h"
#include "api/FragmentApiResultAdapter.hpp"
#include "core/ExecutionResult.hpp"

namespace {

fragment::ExecutionResult make_sample_result() {
    fragment::ExecutionResult result;
    result.success = true;
    result.error_message = "sample-error";
    result.instructions_executed = 42;
    result.memory_accesses = 7;
    result.program_stdout = "sample-stdout";
    result.program_stderr = "sample-stderr";

    result.fd_outputs[3] = fragment::FdCapture{"fd-output", "fd-alias"};
    result.changed_regs.emplace("rax", std::make_pair<uint64_t, uint64_t>(1, 2));

    fragment::MemoryPatch patch;
    patch.address = 0x4000;
    patch.before = {0x11, 0x22};
    patch.after = {0x33, 0x44, 0x55};
    result.memory_patches.push_back(std::move(patch));
    return result;
}

TEST(FragmentApiResultAdapter, CopiesExecutionResultAndReleasesBuffers) {
    const auto result = make_sample_result();

    FE_Result out{};
    ASSERT_TRUE(fragment::api::fill_result_from_execution(result, &out));

    EXPECT_EQ(1, out.success);
    ASSERT_NE(nullptr, out.error_message);
    EXPECT_EQ("sample-error", std::string(out.error_message));
    EXPECT_EQ(42u, out.instructions_executed);
    EXPECT_EQ(7u, out.memory_accesses);

    ASSERT_NE(nullptr, out.program_stdout);
    ASSERT_NE(nullptr, out.program_stderr);
    EXPECT_EQ("sample-stdout", std::string(out.program_stdout));
    EXPECT_EQ("sample-stderr", std::string(out.program_stderr));

    ASSERT_EQ(1u, out.fd_outputs_count);
    ASSERT_NE(nullptr, out.fd_outputs);
    EXPECT_EQ(3, out.fd_outputs[0].fd);
    ASSERT_NE(nullptr, out.fd_outputs[0].alias);
    EXPECT_EQ("fd-alias", std::string(out.fd_outputs[0].alias));
    ASSERT_NE(nullptr, out.fd_outputs[0].data);
    EXPECT_EQ(9u, out.fd_outputs[0].size);
    EXPECT_EQ(std::vector<uint8_t>({'f', 'd', '-', 'o', 'u', 't', 'p', 'u', 't'}),
              std::vector<uint8_t>(out.fd_outputs[0].data, out.fd_outputs[0].data + out.fd_outputs[0].size));

    ASSERT_EQ(1u, out.changed_registers_count);
    ASSERT_NE(nullptr, out.changed_registers);
    ASSERT_NE(nullptr, out.changed_registers[0].name);
    EXPECT_EQ("rax", std::string(out.changed_registers[0].name));
    EXPECT_EQ(1u, out.changed_registers[0].before);
    EXPECT_EQ(2u, out.changed_registers[0].after);

    ASSERT_EQ(1u, out.memory_patches_count);
    ASSERT_NE(nullptr, out.memory_patches);
    EXPECT_EQ(0x4000u, out.memory_patches[0].address);
    ASSERT_EQ(2u, out.memory_patches[0].before_size);
    ASSERT_EQ(3u, out.memory_patches[0].after_size);
    ASSERT_NE(nullptr, out.memory_patches[0].before);
    ASSERT_NE(nullptr, out.memory_patches[0].after);
    EXPECT_EQ(std::vector<uint8_t>({0x11, 0x22}),
              std::vector<uint8_t>(out.memory_patches[0].before,
                                   out.memory_patches[0].before + out.memory_patches[0].before_size));
    EXPECT_EQ(std::vector<uint8_t>({0x33, 0x44, 0x55}),
              std::vector<uint8_t>(out.memory_patches[0].after,
                                   out.memory_patches[0].after + out.memory_patches[0].after_size));

    fragment::api::free_result_buffers(&out);
    EXPECT_EQ(nullptr, out.error_message);
    EXPECT_EQ(nullptr, out.program_stdout);
    EXPECT_EQ(nullptr, out.program_stderr);
    EXPECT_EQ(nullptr, out.fd_outputs);
    EXPECT_EQ(0u, out.fd_outputs_count);
    EXPECT_EQ(nullptr, out.changed_registers);
    EXPECT_EQ(0u, out.changed_registers_count);
    EXPECT_EQ(nullptr, out.memory_patches);
    EXPECT_EQ(0u, out.memory_patches_count);
}

TEST(FragmentApiResultAdapter, HandlesNullAndIsIdempotent) {
    fragment::ExecutionResult result;
    EXPECT_FALSE(fragment::api::fill_result_from_execution(result, nullptr));

    FE_Result out{};
    ASSERT_TRUE(fragment::api::fill_result_from_execution(result, &out));
    fragment::api::free_result_buffers(&out);
    fragment::api::free_result_buffers(&out);
    fragment::api::free_result_buffers(nullptr);
}

}  // namespace
