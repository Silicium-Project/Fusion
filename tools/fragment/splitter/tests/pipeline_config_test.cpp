#include <gtest/gtest.h>

#include "splitter/config.hpp"

TEST(PipelineConfig, Defaults) {
    splitter::PipelineConfig config;
    config.binary_path = "dummy.bin";

    EXPECT_EQ(config.output_dir, std::string("./partitions"));
    EXPECT_EQ(config.function_preview, 20u);
    EXPECT_EQ(config.loop_preview, 10u);
    EXPECT_EQ(config.sample_preview, 5u);
    EXPECT_TRUE(config.dump_full_disassembly);
    EXPECT_FALSE(config.parallel_artifacts);
}
