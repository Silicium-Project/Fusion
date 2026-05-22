#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

#include "worker/io/StructuredRunLogger.hpp"

namespace {

class ScopedEnvVar {
public:
    ScopedEnvVar(const char* key, const std::string& value)
        : key_(key) {
        const char* current = std::getenv(key_);
        had_previous_ = current != nullptr;
        if (had_previous_)
            previous_ = current;
        set(value);
    }

    ~ScopedEnvVar() {
        if (had_previous_) {
            set(previous_);
            return;
        }
#ifdef _WIN32
        _putenv_s(key_, "");
#else
        unsetenv(key_);
#endif
    }

private:
    void set(const std::string& value) const {
#ifdef _WIN32
        _putenv_s(key_, value.c_str());
#else
        setenv(key_, value.c_str(), 1);
#endif
    }

    const char* key_;
    bool had_previous_ = false;
    std::string previous_;
};

std::string read_file(const std::filesystem::path& path) {
    std::ifstream in(path);
    std::string line;
    std::getline(in, line);
    return line;
}

}  // namespace

TEST(StructuredRunLogger, UsesSiliciumRunIdWhenAvailable) {
    ScopedEnvVar run_id("SILICIUM_RUN_ID", "run-cli-91");
    const auto path = std::filesystem::temp_directory_path() / "worker-structured-run-id.ndjson";
    worker::StructuredRunLogger logger(path.string());
    logger.info("task_received", "Task received by worker loop", R"({"task_id":"t1"})");
    EXPECT_EQ("run-cli-91", logger.run_id());
    const std::string line = read_file(path);
    EXPECT_NE(std::string::npos, line.find("\"run_id\":\"run-cli-91\""));
}

TEST(StructuredRunLogger, EmitsSchemaV1Envelope) {
    ScopedEnvVar run_id("WORKER_RUN_ID", "worker-run-42");
    const auto path = std::filesystem::temp_directory_path() / "worker-structured-envelope.ndjson";
    worker::StructuredRunLogger logger(path.string());
    logger.warning("routed", "Task routing decision recorded", R"({"task_id":"part-1","routing_decision":"auto"})");
    const std::string line = read_file(path);
    EXPECT_NE(std::string::npos, line.find("\"schema_version\":1"));
    EXPECT_NE(std::string::npos, line.find("\"component\":\"worker\""));
    EXPECT_NE(std::string::npos, line.find("\"level\":\"warn\""));
    EXPECT_NE(std::string::npos, line.find("\"run_id\":\"worker-run-42\""));
    EXPECT_NE(std::string::npos, line.find("\"event\":\"routed\""));
    EXPECT_NE(std::string::npos, line.find("\"payload\":{\"task_id\":\"part-1\""));
}
