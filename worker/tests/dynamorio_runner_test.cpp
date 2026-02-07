#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "worker/runtime/DynamoRunner.hpp"

namespace {

std::filesystem::path make_tmp_dir(const std::string& name) {
    auto base = std::filesystem::temp_directory_path() / "dyn_runner_tests" / name;
    std::filesystem::create_directories(base);
    return base;
}

}  // namespace

TEST(DynamoRunner, UsesAbsolutePathOutsideWorkspace) {
    auto tmp = make_tmp_dir("abs_path");
    auto log_file = tmp / "log.txt";
    auto launcher = tmp / "launcher.sh";
    {
        std::ofstream out(launcher);
        out << "#!/bin/sh\n"
               "echo \"$@\" >\"" << log_file.string() << "\"\n"
               "exit 0\n";
    }
    std::filesystem::permissions(launcher,
                                 std::filesystem::perms::owner_exec
                                     | std::filesystem::perms::owner_read
                                     | std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::add);

    // Binary path outside repo so it stays absolute in the command.
    const std::string binary = "/bin/echo";

    worker::DynamoRunner runner(launcher.string());
    std::string out, err;
    const bool ok = runner.run_binary(binary, {}, out, err);

    ASSERT_TRUE(ok);
    ASSERT_TRUE(std::filesystem::exists(log_file));
    std::ifstream log(log_file);
    std::string logged;
    std::getline(log, logged);
    EXPECT_NE(std::string::npos, logged.find(binary));
    EXPECT_TRUE(err.empty());
}

TEST(DynamoRunner, NonZeroExitSetsErrorMessage) {
    auto tmp = make_tmp_dir("nonzero");
    auto launcher = tmp / "launcher.sh";
    {
        std::ofstream out(launcher);
        out << "#!/bin/sh\n"
               "exit 5\n";
    }
    std::filesystem::permissions(launcher,
                                 std::filesystem::perms::owner_exec
                                     | std::filesystem::perms::owner_read
                                     | std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::add);

    worker::DynamoRunner runner(launcher.string());
    std::string out, err;
    const bool ok = runner.run_binary("/bin/true", {}, out, err);

    EXPECT_FALSE(ok);
    EXPECT_NE(std::string::npos, err.find("drrun a retourne"));
}
