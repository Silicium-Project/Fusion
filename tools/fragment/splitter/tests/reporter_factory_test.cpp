#include <gtest/gtest.h>

#include <memory>
#include <type_traits>

#include "pipeline/ReporterFactory.hpp"
#include "pipeline/JsonReporter.hpp"
#include "pipeline/ConsoleReporter.hpp"
#include "pipeline/PipelineConfig.hpp"

using namespace splitter;

TEST(ReporterFactory, CreatesJsonReporter) {
    PipelineConfig config;
    config.reporter = "json";
    auto reporter = ReporterFactory::Create(config);
    EXPECT_NE(dynamic_cast<JsonReporter*>(reporter.get()), nullptr);
}

TEST(ReporterFactory, CreatesConsoleReporterByDefault) {
    PipelineConfig config;
    auto reporter = ReporterFactory::Create(config);
    EXPECT_NE(dynamic_cast<ConsoleReporter*>(reporter.get()), nullptr);
}
