#include <gtest/gtest.h>

#include <cstdlib>
#include <string>

#include "support/Env.hpp"
#include "support/ShellCommand.hpp"

namespace splitter {
namespace {

class ScopedEnvVar {
public:
    ScopedEnvVar(std::string key, std::string value)
        : key_(std::move(key)) {
        const auto previous = std::getenv(key_.c_str());
        had_previous_ = previous != nullptr;
        if (had_previous_)
            previous_value_ = previous;
        set(value);
    }

    ~ScopedEnvVar() {
        if (had_previous_) {
            set(previous_value_);
            return;
        }
#ifdef _WIN32
        _putenv_s(key_.c_str(), "");
#else
        unsetenv(key_.c_str());
#endif
    }

private:
    void set(const std::string& value) const {
#ifdef _WIN32
        _putenv_s(key_.c_str(), value.c_str());
#else
        setenv(key_.c_str(), value.c_str(), 1);
#endif
    }

    std::string key_;
    bool had_previous_ = false;
    std::string previous_value_;
};

TEST(SupportEnv, ReturnsValueWhenPresent) {
    ScopedEnvVar scoped("SPLITTER_TEST_ENV_VALUE", "abc123");
    const auto value = GetEnv("SPLITTER_TEST_ENV_VALUE");
    ASSERT_TRUE(value.has_value());
    EXPECT_EQ("abc123", *value);
}

TEST(SupportEnv, ReturnsNulloptWhenMissing) {
#ifdef _WIN32
    _putenv_s("SPLITTER_TEST_ENV_MISSING", "");
#else
    unsetenv("SPLITTER_TEST_ENV_MISSING");
#endif
    EXPECT_FALSE(GetEnv("SPLITTER_TEST_ENV_MISSING").has_value());
}

TEST(ShellCommand, CapturesStdoutAndStderr) {
    const auto output = ExecCommand("sh -c 'echo out && echo err 1>&2'");
    EXPECT_NE(std::string::npos, output.find("out"));
    EXPECT_NE(std::string::npos, output.find("err"));
}

TEST(ShellCommand, ThrowsOnFailingCommand) {
    EXPECT_THROW(ExecCommand("sh -c 'echo fail && exit 7'"), std::runtime_error);
}

}  // namespace
}  // namespace splitter
