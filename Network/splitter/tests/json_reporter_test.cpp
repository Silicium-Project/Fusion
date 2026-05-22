#include <gtest/gtest.h>

#include <cstdlib>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "pipeline/JsonReporter.hpp"

using namespace splitter;

namespace {

class ScopedEnvVar {
public:
    ScopedEnvVar(std::string key, std::string value) : key_(std::move(key)) {
        if (const char* current = std::getenv(key_.c_str())) {
            had_previous_ = true;
            previous_value_ = current;
        }
        set_value(std::move(value));
    }

    ~ScopedEnvVar() {
        if (had_previous_) {
            set_value(previous_value_);
        } else {
            unset_value();
        }
    }

private:
    void set_value(const std::string& value) {
#ifdef _WIN32
        _putenv_s(key_.c_str(), value.c_str());
#else
        setenv(key_.c_str(), value.c_str(), 1);
#endif
    }

    void unset_value() {
#ifdef _WIN32
        _putenv_s(key_.c_str(), "");
#else
        unsetenv(key_.c_str());
#endif
    }

    std::string key_;
    std::string previous_value_;
    bool had_previous_ = false;
};

}  // namespace

TEST(JsonReporter, StructuredInfoEventContainsSchemaV1Fields) {
    const ScopedEnvVar run_id("SPLITTER_RUN_ID", "run-test-42");
    auto out = std::make_shared<std::ostringstream>();
    JsonReporter reporter(out, JsonReporter::Mode::StructuredV1Ndjson);

    reporter.Info("hello");

    const std::string log = out->str();
    EXPECT_NE(log.find("\"schema_version\":1"), std::string::npos);
    EXPECT_NE(log.find("\"component\":\"splitter\""), std::string::npos);
    EXPECT_NE(log.find("\"level\":\"info\""), std::string::npos);
    EXPECT_NE(log.find("\"run_id\":\"run-test-42\""), std::string::npos);
    EXPECT_NE(log.find("\"event\":\"info\""), std::string::npos);
    EXPECT_NE(log.find("\"message\":\"hello\""), std::string::npos);
    EXPECT_NE(log.find("\"payload\":{}"), std::string::npos);
}

TEST(JsonReporter, StructuredLifecycleEventsContainArtifactsAndDurations) {
    const ScopedEnvVar run_id("SPLITTER_RUN_ID", "run-lifecycle-1");
    auto out = std::make_shared<std::ostringstream>();
    JsonReporter reporter(out, JsonReporter::Mode::StructuredV1Ndjson);

    const std::vector<std::string> inputs = {"input.bin", "deps/index.txt"};
    const std::vector<std::string> outputs = {"summary.json"};

    reporter.ReportPhaseStart("analysis", inputs, outputs);
    reporter.ReportPhaseCompleted("analysis", inputs, outputs, 12);
    reporter.ReportPhaseFailed("analysis", inputs, outputs, 34, "boom", 7);

    const std::string log = out->str();
    EXPECT_NE(log.find("\"event\":\"phase_started\""), std::string::npos);
    EXPECT_NE(log.find("\"event\":\"phase_completed\""), std::string::npos);
    EXPECT_NE(log.find("\"event\":\"phase_failed\""), std::string::npos);
    EXPECT_NE(log.find("\"phase\":\"analysis\""), std::string::npos);
    EXPECT_NE(log.find("\"input_artifacts\":[\"input.bin\",\"deps/index.txt\"]"), std::string::npos);
    EXPECT_NE(log.find("\"output_artifacts\":[\"summary.json\"]"), std::string::npos);
    EXPECT_NE(log.find("\"duration_ms\":12"), std::string::npos);
    EXPECT_NE(log.find("\"duration_ms\":34"), std::string::npos);
    EXPECT_NE(log.find("\"error\":\"boom\""), std::string::npos);
    EXPECT_NE(log.find("\"error_code\":7"), std::string::npos);
}

TEST(JsonReporter, LegacyModeKeepsExistingFormat) {
    auto out = std::make_shared<std::ostringstream>();
    JsonReporter reporter(out, JsonReporter::Mode::LegacyJson);

    reporter.Info("legacy");
    reporter.ReportRunStart("demo.bin", "out");

    EXPECT_EQ(out->str(), "{\"type\":\"info\",\"message\":\"legacy\"}\n");
}
