#include <gtest/gtest.h>

#include "pipeline/PipelineConfig.hpp"

TEST(PipelineConfig, Defaults) {
    splitter::PipelineConfig config;
    config.binary_path = splitter::BinaryPath("dummy.bin");

    EXPECT_EQ(config.output_dir.Value(), std::string("./partitions"));
    EXPECT_EQ(config.function_preview, 20u);
    EXPECT_EQ(config.loop_preview, 10u);
    EXPECT_EQ(config.sample_preview, 5u);
    EXPECT_TRUE(config.dump_full_disassembly);
    EXPECT_FALSE(config.parallel_artifacts);
    EXPECT_EQ(config.reporter, "console");
    EXPECT_TRUE(config.report_file.empty());
}
