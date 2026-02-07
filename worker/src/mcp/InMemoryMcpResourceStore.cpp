#include "worker/mcp/InMemoryMcpResourceStore.hpp"

#include <sstream>

namespace worker::mcp {

namespace {

constexpr const char* kResultByTaskPrefix = "resources://silicium/results/by-task/";
constexpr const char* kLogsByTaskPrefix = "resources://silicium/logs/by-task/";

bool has_prefix(const std::string& value, const std::string& prefix) {
    if (value.size() < prefix.size())
        return false;
    return value.compare(0, prefix.size(), prefix) == 0;
}

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

std::string serialize_envelope(const McpEnvelope& envelope) {
    std::ostringstream oss;
    oss << "{"
        << "\"schema_version\":" << envelope.schema_version << ","
        << "\"event_id\":\"" << escape_json(envelope.event_id) << "\","
        << "\"timestamp_utc\":\"" << escape_json(envelope.timestamp_utc) << "\","
        << "\"source\":\"" << escape_json(envelope.source) << "\","
        << "\"kind\":\"" << escape_json(std::string(to_string(envelope.kind))) << "\","
        << "\"task_id\":\"" << escape_json(envelope.task_id) << "\","
        << "\"payload\":" << envelope.payload_json
        << "}";
    return oss.str();
}

std::string error_json(const std::string& code, const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
        << "\"error_code\":\"" << escape_json(code) << "\","
        << "\"message\":\"" << escape_json(message) << "\""
        << "}";
    return oss.str();
}

}  // namespace

InMemoryMcpResourceStore::InMemoryMcpResourceStore(std::size_t max_recent_events)
: max_recent_events_(max_recent_events ? max_recent_events : 1),
  current_status_json_("{\"schema_version\":1,\"status\":\"unknown\"}") {}

void InMemoryMcpResourceStore::upsert_from_event(const McpEnvelope& envelope) {
    if (!can_publish(envelope))
        return;

    std::lock_guard<std::mutex> lock(mutex_);

    if (envelope.kind == McpEventKind::WorkerStatus)
        current_status_json_ = envelope.payload_json;

    if (envelope.kind == McpEventKind::TaskFinished && !envelope.task_id.empty()) {
        task_result_payloads_[envelope.task_id] = envelope.payload_json;
        task_log_payloads_[envelope.task_id] = envelope.payload_json;
    }

    recent_event_envelopes_.push_back(serialize_envelope(envelope));
    while (recent_event_envelopes_.size() > max_recent_events_) {
        recent_event_envelopes_.pop_front();
    }
}

std::string InMemoryMcpResourceStore::read_resource(const std::string& resource_uri) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (resource_uri == std::string(kResourceStatusCurrent))
        return current_status_json_;

    if (resource_uri == std::string(kResourceReportsRecent)) {
        std::ostringstream oss;
        oss << "{"
            << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
            << "\"events\":[";
        for (std::size_t i = 0; i < recent_event_envelopes_.size(); ++i) {
            if (i)
                oss << ",";
            oss << recent_event_envelopes_[i];
        }
        oss << "]}";
        return oss.str();
    }

    if (has_prefix(resource_uri, kResultByTaskPrefix)) {
        const std::string task_id = resource_uri.substr(std::char_traits<char>::length(kResultByTaskPrefix));
        if (task_id.empty())
            return error_json("bad_request", "missing task id");
        const auto it = task_result_payloads_.find(task_id);
        if (it == task_result_payloads_.end())
            return error_json("not_found", "result not found");
        return it->second;
    }

    if (has_prefix(resource_uri, kLogsByTaskPrefix)) {
        const std::string task_id = resource_uri.substr(std::char_traits<char>::length(kLogsByTaskPrefix));
        if (task_id.empty())
            return error_json("bad_request", "missing task id");
        const auto it = task_log_payloads_.find(task_id);
        if (it == task_log_payloads_.end())
            return error_json("not_found", "logs not found");
        return it->second;
    }

    return error_json("unsupported_resource", "resource is not supported");
}

}  // namespace worker::mcp
