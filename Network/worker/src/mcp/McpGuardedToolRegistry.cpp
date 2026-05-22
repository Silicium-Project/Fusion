#include "worker/mcp/McpGuardedToolRegistry.hpp"

#include <chrono>
#include <functional>
#include <jansson.h>
#include <memory>
#include <optional>
#include <sstream>
#include <string_view>
#include <stdexcept>

namespace worker::mcp {

namespace {

using JsonHandle = std::unique_ptr<json_t, decltype(&json_decref)>;

JsonHandle parse_json_object(const std::string& payload) {
    json_error_t err;
    JsonHandle root(json_loads(payload.c_str(), 0, &err), &json_decref);
    if (!root)
        throw std::runtime_error("invalid_json");
    if (!json_is_object(root.get()))
        throw std::runtime_error("invalid_json_object");
    return root;
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

std::string tool_error_json(const std::string& code,
                            const std::string& tool_name,
                            const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
        << "\"error_code\":\"" << escape_json(code) << "\","
        << "\"tool\":\"" << escape_json(tool_name) << "\","
        << "\"message\":\"" << escape_json(message) << "\""
        << "}";
    return oss.str();
}

std::string tool_ack_json(const std::string& tool_name,
                          const std::string& status,
                          const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
        << "\"tool\":\"" << escape_json(tool_name) << "\","
        << "\"status\":\"" << escape_json(status) << "\","
        << "\"message\":\"" << escape_json(message) << "\""
        << "}";
    return oss.str();
}

std::string parse_json_string_field(const std::string& json_payload,
                                    std::string_view key,
                                    std::optional<std::reference_wrapper<bool>> has_field = std::nullopt) {
    if (has_field.has_value())
        has_field->get() = false;
    if (json_payload.empty())
        return "";

    auto root = parse_json_object(json_payload);
    std::string out;
    const std::string key_copy(key);
    if (auto value = json_object_get(root.get(), key_copy.c_str()); json_is_string(value)) {
        out = json_string_value(value);
        if (has_field.has_value())
            has_field->get() = true;
    }
    return out;
}

std::optional<ExecutionMode> parse_execution_mode_name(const std::string& value) {
    if (value == "auto")
        return ExecutionMode::Auto;
    if (value == "emu")
        return ExecutionMode::Emulator;
    if (value == "native")
        return ExecutionMode::Native;
    if (value == "dynamo")
        return ExecutionMode::Dynamo;
    return std::nullopt;
}

}  // namespace

McpGuardedToolRegistry::McpGuardedToolRegistry(std::shared_ptr<IMcpResourceStore> store,
                                               McpToolRegistryConfig config)
: store_(std::move(store)),
  config_(config) {}

std::string McpGuardedToolRegistry::execute_tool(const std::string& tool_name,
                                                 const std::string& args_json) {
    const auto start = std::chrono::steady_clock::now();
    bool failed = false;
    std::string failure_code;
    std::string response;

    if (!is_supported_tool(tool_name)) {
        failed = true;
        failure_code = "unsupported_tool";
        response = tool_error_json(failure_code, tool_name, "tool is not supported");
    } else if (tool_name == std::string(kToolGetHealth)) {
        if (!store_) {
            failed = true;
            failure_code = "store_unavailable";
            response = tool_error_json(failure_code, tool_name, "resource store is unavailable");
        } else {
            response = store_->read_resource(std::string(kResourceStatusCurrent));
        }
    } else if (!config_.enable_control_tools) {
        failed = true;
        failure_code = "tool_disabled";
        response = tool_error_json(failure_code, tool_name, "control tools are disabled by policy");
    } else if (tool_name == std::string(kToolRunAction)) {
        if (!store_) {
            failed = true;
            failure_code = "store_unavailable";
            response = tool_error_json(failure_code, tool_name, "resource store is unavailable");
        } else {
            try {
                bool has_action = false;
                const std::string action = parse_json_string_field(args_json, "action", std::ref(has_action));
                if (!has_action || action.empty()) {
                    failed = true;
                    failure_code = "bad_request";
                    response = tool_error_json(failure_code, tool_name, "missing action");
                } else if (action == "get_health_snapshot") {
                    response = store_->read_resource(std::string(kResourceStatusCurrent));
                } else if (action == "read_recent_reports") {
                    response = store_->read_resource(std::string(kResourceReportsRecent));
                } else if (action == "read_task_result") {
                    bool has_task_id = false;
                    const std::string task_id = parse_json_string_field(args_json, "task_id", std::ref(has_task_id));
                    if (!has_task_id || task_id.empty()) {
                        failed = true;
                        failure_code = "bad_request";
                        response = tool_error_json(failure_code, tool_name, "missing task_id");
                    } else {
                        response = store_->read_resource(
                            std::string("resources://silicium/results/by-task/") + task_id);
                    }
                } else {
                    failed = true;
                    failure_code = "action_not_allowed";
                    response = tool_error_json(failure_code, tool_name, "action is not allowed");
                }
            } catch (const std::runtime_error&) {
                failed = true;
                failure_code = "bad_request";
                response = tool_error_json(failure_code, tool_name, "invalid args_json");
            }
        }
    } else if (tool_name == std::string(kToolInterruptAction)) {
        {
            std::lock_guard<std::mutex> lock(control_mutex_);
            interrupt_requested_ = true;
        }
        response = tool_ack_json(tool_name, "accepted", "interrupt request registered");
    } else if (tool_name == std::string(kToolSelectRunnerMode)) {
        try {
            bool has_mode = false;
            const std::string mode_name = parse_json_string_field(args_json, "mode", std::ref(has_mode));
            if (!has_mode || mode_name.empty()) {
                failed = true;
                failure_code = "bad_request";
                response = tool_error_json(failure_code, tool_name, "missing mode");
            } else {
                const auto mode = parse_execution_mode_name(mode_name);
                if (!mode.has_value()) {
                    failed = true;
                    failure_code = "bad_request";
                    response = tool_error_json(failure_code, tool_name, "unsupported mode");
                } else {
                    {
                        std::lock_guard<std::mutex> lock(control_mutex_);
                        requested_mode_ = *mode;
                    }
                    response = tool_ack_json(tool_name, "accepted", "runner mode request registered");
                }
            }
        } catch (const std::runtime_error&) {
            failed = true;
            failure_code = "bad_request";
            response = tool_error_json(failure_code, tool_name, "invalid args_json");
        }
    } else {
        failed = true;
        failure_code = "unsupported_tool";
        response = tool_error_json(failure_code, tool_name, "tool is not supported");
    }

    const auto end = std::chrono::steady_clock::now();
    const auto latency_ms = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count());

    {
        std::lock_guard<std::mutex> lock(metrics_mutex_);
        ++metrics_.calls;
        metrics_.last_latency_ms = latency_ms;
        if (failed) {
            ++metrics_.failures;
            metrics_.last_error = failure_code;
        } else {
            metrics_.last_error.clear();
        }
    }

    return response;
}

McpToolMetrics McpGuardedToolRegistry::snapshot_metrics() const {
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    return metrics_;
}

bool McpGuardedToolRegistry::consume_interrupt_request() {
    std::lock_guard<std::mutex> lock(control_mutex_);
    const bool value = interrupt_requested_;
    interrupt_requested_ = false;
    return value;
}

std::optional<ExecutionMode> McpGuardedToolRegistry::consume_mode_request() {
    std::lock_guard<std::mutex> lock(control_mutex_);
    const auto out = requested_mode_;
    requested_mode_.reset();
    return out;
}

}  // namespace worker::mcp
