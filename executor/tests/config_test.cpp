#include <gtest/gtest.h>

#include "core/Config.hpp"

using fragment::ExecutorConfig;

TEST(ExecutorConfig, Defaults) {
    ExecutorConfig cfg;
    EXPECT_FALSE(cfg.use_native_execution);
    EXPECT_TRUE(cfg.fd_rules.empty());
    EXPECT_EQ(cfg.emulated_stack_size, static_cast<std::size_t>(1 << 20));
    EXPECT_TRUE(cfg.binary_path.empty());
}
