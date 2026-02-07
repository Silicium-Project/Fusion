#include <gtest/gtest.h>

#include <memory>
#include <string>

#include "worker/mcp/IMcpConnectorAdapter.hpp"
#include "worker/mcp/McpEnvelope.hpp"
#include "worker/mcp/McpSchema.hpp"

namespace worker::mcp {
namespace {

class NullMcpConnectorAdapter : public IMcpConnectorAdapter {
public:
    void on_task_start(const TaskContext& context, const Task& task) override {
        (void)context;
        (void)task;
    }

    void on_task_finish(const TaskContext& context, const Task& task, const TaskReport& report) override {
        (void)context;
        (void)task;
        (void)report;
    }

    void publish_worker_report(const WorkerReport& report) override {
        (void)report;
    }

    std::string read_resource(const std::string& resource_uri) const override {
        return resource_uri;
    }

    std::string execute_tool(const std::string& tool_name, const std::string& args_json) override {
        return tool_name + ":" + args_json;
    }
};

}  // namespace

TEST(McpSchema, UsesStableSchemaVersion) {
    EXPECT_EQ(1u, kMcpEnvelopeSchemaVersion);
    EXPECT_TRUE(is_supported_schema_version(kMcpEnvelopeSchemaVersion));
    EXPECT_FALSE(is_supported_schema_version(999u));
}

TEST(McpSchema, EventKindRoundTrip) {
    ASSERT_EQ("task_started", to_string(McpEventKind::TaskStarted));
    ASSERT_EQ("task_finished", to_string(McpEventKind::TaskFinished));
    ASSERT_EQ("worker_status", to_string(McpEventKind::WorkerStatus));
    ASSERT_EQ("connector_decision", to_string(McpEventKind::ConnectorDecision));
    ASSERT_EQ("error", to_string(McpEventKind::Error));

    ASSERT_EQ(McpEventKind::TaskStarted, parse_event_kind("task_started").value());
    ASSERT_EQ(McpEventKind::TaskFinished, parse_event_kind("task_finished").value());
    ASSERT_EQ(McpEventKind::WorkerStatus, parse_event_kind("worker_status").value());
    ASSERT_EQ(McpEventKind::ConnectorDecision, parse_event_kind("connector_decision").value());
    ASSERT_EQ(McpEventKind::Error, parse_event_kind("error").value());
    EXPECT_FALSE(parse_event_kind("unknown_kind").has_value());
}

TEST(McpSchema, SupportedToolsAndResources) {
    EXPECT_TRUE(is_supported_tool(kToolRunAction));
    EXPECT_TRUE(is_supported_tool(kToolInterruptAction));
    EXPECT_TRUE(is_supported_tool(kToolSelectRunnerMode));
    EXPECT_TRUE(is_supported_tool(kToolGetHealth));
    EXPECT_FALSE(is_supported_tool("tools.silicium.unknown"));

    EXPECT_TRUE(is_supported_resource(kResourceStatusCurrent));
    EXPECT_TRUE(is_supported_resource(kResourceReportsRecent));
    EXPECT_TRUE(is_supported_resource(kResourceResultByTask));
    EXPECT_TRUE(is_supported_resource(kResourceLogsByTask));
    EXPECT_FALSE(is_supported_resource("resources://silicium/unknown"));
}

TEST(McpSchema, EnvelopePublishValidation) {
    McpEnvelope envelope{};
    EXPECT_FALSE(can_publish(envelope));

    envelope.event_id = "evt-1";
    envelope.timestamp_utc = "2026-02-07T00:00:00Z";
    envelope.source = "worker";
    envelope.kind = McpEventKind::TaskFinished;
    envelope.payload_json = "{}";
    EXPECT_TRUE(can_publish(envelope));
}

TEST(McpSchema, AdapterInterfaceCanBeImplemented) {
    std::unique_ptr<IMcpConnectorAdapter> adapter = std::make_unique<NullMcpConnectorAdapter>();
    ASSERT_NE(nullptr, adapter);
    EXPECT_EQ("resources://silicium/status/current", adapter->read_resource("resources://silicium/status/current"));
    EXPECT_EQ("tools.silicium.get_health:{}", adapter->execute_tool("tools.silicium.get_health", "{}"));
}

}  // namespace worker::mcp
