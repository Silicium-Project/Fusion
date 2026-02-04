#include <gtest/gtest.h>

#include "worker/core/WorkerConfig.hpp"

namespace worker {

TEST(WslTriggers, DisabledByDefault) {
    WslTriggerConfig config;
    std::string reason;
    EXPECT_FALSE(evaluate_wsl_triggers(config, &reason));
    EXPECT_EQ(reason, "disabled");
}

TEST(WslTriggers, RequiresThresholds) {
    WslTriggerConfig config;
    config.enabled = true;
    config.min_reward = 10.0;
    config.min_jobs = 2;

    config.current_reward = 5.0;
    config.available_jobs = 5;
    std::string reason;
    EXPECT_FALSE(evaluate_wsl_triggers(config, &reason));
    EXPECT_EQ(reason, "reward_below_threshold");

    config.current_reward = 12.0;
    config.available_jobs = 1;
    EXPECT_FALSE(evaluate_wsl_triggers(config, &reason));
    EXPECT_EQ(reason, "jobs_below_threshold");

    config.available_jobs = 3;
    EXPECT_TRUE(evaluate_wsl_triggers(config, &reason));
    EXPECT_EQ(reason, "enabled");
}

}  // namespace worker
