#include <gtest/gtest.h>

#include "worker/executor_client.hpp"

TEST(ExecutorClient, MissingLibraryThrows) {
    EXPECT_THROW(worker::ExecutorClient("/tmp/does_not_exist_executor.so"), std::runtime_error);
}
