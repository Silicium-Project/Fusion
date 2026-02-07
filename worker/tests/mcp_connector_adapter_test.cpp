#include <gtest/gtest.h>

#include <memory>
#include <string>

#include "worker/mcp/IMcpEventSink.hpp"
#include "worker/mcp/InMemoryMcpResourceStore.hpp"
#include "worker/mcp/McpReadOnlyConnectorAdapter.hpp"

namespace worker::mcp {
namespace {

class CountingSink : public IMcpEventSink {
public:
    void publish_event(const McpEnvelope& envelope) override {
        ++count;
        last_kind = envelope.kind;
        last_task_id = envelope.task_id;
    }

    int count = 0;
    McpEventKind last_kind = McpEventKind::Error;
    std::string last_task_id;
};

TaskContext make_context(const std::string& partition_id) {
    fragment::PartitionInfo partition;
    partition.id = partition_id;
    partition.os = "linux";
    partition.format = "elf";
    return TaskContext{partition, "/tmp/a.asm", "/tmp/a.bin", "/tmp/summary.json"};
}

Task make_binary_task(const std::string& task_id) {
    Task task;
    task.type = TaskType::Binary;
    task.partition_id = task_id;
    return task;
}

TaskReport make_success_report(const std::string& partition_id, const std::string& task_id) {
    TaskReport report;
    report.partition_id = partition_id;
    report.telemetry.task_id = task_id;
    report.telemetry.type = TaskType::Binary;
    report.telemetry.status = "success";
    report.telemetry.duration_ms = 42;
    report.result.success = true;
    report.result.program_stdout = "ok";
    return report;
}

}  // namespace

TEST(McpConnectorAdapter, ExposesTaskEventsAsReadOnlyResources) {
    auto store = std::make_shared<InMemoryMcpResourceStore>();
    auto sink = std::make_shared<CountingSink>();
    McpReadOnlyConnectorAdapter adapter(store, sink);

    const TaskContext context = make_context("p1");
    const Task task = make_binary_task("task-1");

    adapter.on_task_start(context, task);
    adapter.on_task_finish(context, task, make_success_report("p1", "task-1"));

    const std::string recent = adapter.read_resource(std::string(kResourceReportsRecent));
    EXPECT_NE(std::string::npos, recent.find("\"kind\":\"task_started\""));
    EXPECT_NE(std::string::npos, recent.find("\"kind\":\"task_finished\""));
    EXPECT_NE(std::string::npos, recent.find("\"task_id\":\"task-1\""));

    const std::string result = adapter.read_resource("resources://silicium/results/by-task/task-1");
    EXPECT_NE(std::string::npos, result.find("\"success\":true"));
    EXPECT_NE(std::string::npos, result.find("\"stdout\":\"ok\""));

    const std::string logs = adapter.read_resource("resources://silicium/logs/by-task/task-1");
    EXPECT_NE(std::string::npos, logs.find("\"stdout\":\"ok\""));

    EXPECT_EQ(2, sink->count);
    EXPECT_EQ(McpEventKind::TaskFinished, sink->last_kind);
    EXPECT_EQ("task-1", sink->last_task_id);
}

TEST(McpConnectorAdapter, PublishesWorkerStatusResource) {
    McpReadOnlyConnectorAdapter adapter;

    WorkerReport report;
    report.summary_path = "/tmp/summary.json";
    report.mode = ExecutionMode::Emulator;
    report.tasks.push_back(make_success_report("p2", "task-2"));
    adapter.publish_worker_report(report);

    const std::string status = adapter.read_resource(std::string(kResourceStatusCurrent));
    EXPECT_NE(std::string::npos, status.find("\"summary\":\"/tmp/summary.json\""));
    EXPECT_NE(std::string::npos, status.find("\"task_id\":\"task-2\""));
}

TEST(McpConnectorAdapter, ToolExecutionIsDisabledInReadOnlyMode) {
    McpReadOnlyConnectorAdapter adapter;
    const std::string out = adapter.execute_tool(std::string(kToolRunAction), "{}");
    EXPECT_NE(std::string::npos, out.find("\"error_code\":\"tool_disabled\""));
    EXPECT_NE(std::string::npos, out.find("\"tool\":\"tools.silicium.run_action\""));
}

TEST(McpConnectorAdapter, GetHealthToolReturnsStatusResource) {
    McpReadOnlyConnectorAdapter adapter;

    WorkerReport report;
    report.summary_path = "/tmp/summary-health.json";
    report.mode = ExecutionMode::Emulator;
    report.tasks.push_back(make_success_report("p3", "task-3"));
    adapter.publish_worker_report(report);

    const std::string out = adapter.execute_tool(std::string(kToolGetHealth), "{}");
    EXPECT_NE(std::string::npos, out.find("\"summary\":\"/tmp/summary-health.json\""));
    EXPECT_NE(std::string::npos, out.find("\"task_id\":\"task-3\""));
}

TEST(McpConnectorAdapter, ControlToolsCanBeGuardEnabled) {
    McpReadOnlyAdapterOptions options{};
    options.enable_control_tools = true;
    McpReadOnlyConnectorAdapter adapter(nullptr, nullptr, options);

    const std::string out = adapter.execute_tool(std::string(kToolInterruptAction), "{\"task_id\":\"t\"}");
    EXPECT_NE(std::string::npos, out.find("\"status\":\"not_implemented\""));
    EXPECT_NE(std::string::npos, out.find("\"tool\":\"tools.silicium.interrupt_action\""));
}

TEST(McpConnectorAdapter, RunActionAllowlistReadsResources) {
    McpReadOnlyAdapterOptions options{};
    options.enable_control_tools = true;
    McpReadOnlyConnectorAdapter adapter(nullptr, nullptr, options);

    WorkerReport report;
    report.summary_path = "/tmp/summary-allowlist.json";
    report.mode = ExecutionMode::Emulator;
    report.tasks.push_back(make_success_report("p4", "task-allow"));
    adapter.publish_worker_report(report);
    const TaskContext context = make_context("p4");
    const Task task = make_binary_task("task-allow");
    adapter.on_task_finish(context, task, make_success_report("p4", "task-allow"));

    const std::string health = adapter.execute_tool(
        std::string(kToolRunAction), "{\"action\":\"get_health_snapshot\"}");
    EXPECT_NE(std::string::npos, health.find("\"summary\":\"/tmp/summary-allowlist.json\""));

    const std::string recent = adapter.execute_tool(
        std::string(kToolRunAction), "{\"action\":\"read_recent_reports\"}");
    EXPECT_NE(std::string::npos, recent.find("\"events\""));

    const std::string result = adapter.execute_tool(
        std::string(kToolRunAction), "{\"action\":\"read_task_result\",\"task_id\":\"task-allow\"}");
    EXPECT_NE(std::string::npos, result.find("\"success\":true"));
}

TEST(McpConnectorAdapter, ToolMetricsTrackFailures) {
    McpReadOnlyAdapterOptions options{};
    options.enable_control_tools = true;
    McpReadOnlyConnectorAdapter adapter(nullptr, nullptr, options);

    const std::string err = adapter.execute_tool(
        std::string(kToolRunAction), "{\"action\":\"not_allowed\"}");
    EXPECT_NE(std::string::npos, err.find("\"error_code\":\"action_not_allowed\""));

    const auto metrics = adapter.snapshot_metrics();
    EXPECT_GE(metrics.calls, 1u);
    EXPECT_GE(metrics.failures, 1u);
    EXPECT_EQ("action_not_allowed", metrics.last_error);
}

TEST(McpConnectorAdapter, MissingResultReturnsNotFound) {
    McpReadOnlyConnectorAdapter adapter;
    const std::string out = adapter.read_resource("resources://silicium/results/by-task/missing");
    EXPECT_NE(std::string::npos, out.find("\"error_code\":\"not_found\""));
}

}  // namespace worker::mcp
