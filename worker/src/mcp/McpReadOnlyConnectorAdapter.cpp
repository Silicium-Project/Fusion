#include "worker/mcp/McpReadOnlyConnectorAdapter.hpp"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

#include "worker/io/Reporter.hpp"
#include "worker/mcp/InMemoryMcpResourceStore.hpp"
#include "worker/mcp/McpGuardedToolRegistry.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker::mcp {

namespace {

std::string escape_json(std::string_view value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (const char ch : value) {
        switch (ch) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out.push_back(ch);
            break;
        }
    }
    return out;
}

std::string timestamp_utc_now() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm_utc{};
#if defined(_WIN32)
    gmtime_s(&tm_utc, &time);
#else
    gmtime_r(&time, &tm_utc);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_utc, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

std::string make_task_id(const TaskContext& context, const Task& task) {
    if (!task.partition_id.empty())
        return task.partition_id;
    if (!context.partition.id.empty())
        return context.partition.id;
    return "task";
}

}  // namespace

McpReadOnlyConnectorAdapter::McpReadOnlyConnectorAdapter()
: McpReadOnlyConnectorAdapter(std::make_shared<InMemoryMcpResourceStore>()) {}

McpReadOnlyConnectorAdapter::McpReadOnlyConnectorAdapter(std::shared_ptr<IMcpResourceStore> store)
: McpReadOnlyConnectorAdapter(std::move(store), nullptr, {}) {}

McpReadOnlyConnectorAdapter::McpReadOnlyConnectorAdapter(std::shared_ptr<IMcpResourceStore> store,
                                                         std::shared_ptr<IMcpEventSink> event_sink,
                                                         McpReadOnlyAdapterOptions options)
: store_(std::move(store)),
  event_sink_(std::move(event_sink)) {
    if (!store_)
        store_ = std::make_shared<InMemoryMcpResourceStore>();
    guarded_tool_registry_ = std::make_shared<McpGuardedToolRegistry>(
        store_, McpToolRegistryConfig{options.enable_control_tools});
    tool_registry_ = guarded_tool_registry_;
}

void McpReadOnlyConnectorAdapter::on_task_start(const TaskContext& context, const Task& task) {
    const std::string task_id = make_task_id(context, task);
    std::ostringstream payload;
    payload << "{"
            << "\"partition\":\"" << escape_json(context.partition.id) << "\","
            << "\"type\":\"" << escape_json(task_type_to_string(task.type)) << "\","
            << "\"status\":\"running\""
            << "}";

    McpEnvelope envelope;
    envelope.schema_version = kMcpEnvelopeSchemaVersion;
    envelope.event_id = "evt-" + std::to_string(++sequence_);
    envelope.timestamp_utc = timestamp_utc_now();
    envelope.source = "worker.mcp.read_only_adapter";
    envelope.kind = McpEventKind::TaskStarted;
    envelope.task_id = task_id;
    envelope.payload_json = payload.str();
    publish_event(std::move(envelope));
}

void McpReadOnlyConnectorAdapter::on_task_finish(const TaskContext& context,
                                                 const Task& task,
                                                 const TaskReport& report) {
    const std::string task_id = make_task_id(context, task);
    std::ostringstream payload;
    payload << "{"
            << "\"partition\":\"" << escape_json(report.partition_id) << "\","
            << "\"type\":\"" << escape_json(task_type_to_string(report.telemetry.type)) << "\","
            << "\"status\":\"" << escape_json(report.telemetry.status.empty()
                    ? (report.result.success ? "success" : "failure")
                    : report.telemetry.status) << "\","
            << "\"success\":" << (report.result.success ? "true" : "false") << ","
            << "\"duration_ms\":" << report.telemetry.duration_ms << ","
            << "\"error\":\"" << escape_json(report.result.error_message) << "\","
            << "\"stdout\":\"" << escape_json(report.result.program_stdout) << "\","
            << "\"stderr\":\"" << escape_json(report.result.program_stderr) << "\""
            << "}";

    McpEnvelope envelope;
    envelope.schema_version = kMcpEnvelopeSchemaVersion;
    envelope.event_id = "evt-" + std::to_string(++sequence_);
    envelope.timestamp_utc = timestamp_utc_now();
    envelope.source = "worker.mcp.read_only_adapter";
    envelope.kind = McpEventKind::TaskFinished;
    envelope.task_id = task_id;
    envelope.payload_json = payload.str();
    publish_event(std::move(envelope));
}

void McpReadOnlyConnectorAdapter::publish_worker_report(const WorkerReport& report) {
    std::ostringstream report_json;
    Reporter reporter(OutputFormat::Json, report_json);
    reporter.emit(report);

    McpEnvelope envelope;
    envelope.schema_version = kMcpEnvelopeSchemaVersion;
    envelope.event_id = "evt-" + std::to_string(++sequence_);
    envelope.timestamp_utc = timestamp_utc_now();
    envelope.source = "worker.mcp.read_only_adapter";
    envelope.kind = McpEventKind::WorkerStatus;
    envelope.payload_json = report_json.str();
    publish_event(std::move(envelope));
}

std::string McpReadOnlyConnectorAdapter::read_resource(const std::string& resource_uri) const {
    return store_->read_resource(resource_uri);
}

std::string McpReadOnlyConnectorAdapter::execute_tool(const std::string& tool_name,
                                                      const std::string& args_json) {
    if (!tool_registry_) {
        std::ostringstream oss;
        oss << "{"
            << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
            << "\"error_code\":\"tool_registry_unavailable\","
            << "\"tool\":\"" << escape_json(tool_name) << "\","
            << "\"message\":\"tool registry is unavailable\""
            << "}";
        return oss.str();
    }
    return tool_registry_->execute_tool(tool_name, args_json);
}

McpAdapterMetrics McpReadOnlyConnectorAdapter::snapshot_metrics() const {
    if (!guarded_tool_registry_)
        return {};
    return guarded_tool_registry_->snapshot_metrics();
}

void McpReadOnlyConnectorAdapter::publish_event(McpEnvelope envelope) {
    store_->upsert_from_event(envelope);
    if (!event_sink_)
        return;
    event_sink_->publish_event(envelope);
}

}  // namespace worker::mcp
