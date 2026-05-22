#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string_view>

namespace worker::mcp {

inline constexpr std::uint32_t kMcpEnvelopeSchemaVersion = 1;

enum class McpEventKind {
    TaskStarted,
    TaskFinished,
    WorkerStatus,
    ConnectorDecision,
    Error
};

inline constexpr std::string_view kToolRunAction = "tools.silicium.run_action";
inline constexpr std::string_view kToolInterruptAction = "tools.silicium.interrupt_action";
inline constexpr std::string_view kToolSelectRunnerMode = "tools.silicium.select_runner_mode";
inline constexpr std::string_view kToolGetHealth = "tools.silicium.get_health";

inline constexpr std::string_view kResourceStatusCurrent = "resources://silicium/status/current";
inline constexpr std::string_view kResourceReportsRecent = "resources://silicium/reports/recent";
inline constexpr std::string_view kResourceResultByTask = "resources://silicium/results/by-task/{task_id}";
inline constexpr std::string_view kResourceLogsByTask = "resources://silicium/logs/by-task/{task_id}";

inline constexpr std::array<std::string_view, 4> kSupportedTools{
    kToolRunAction,
    kToolInterruptAction,
    kToolSelectRunnerMode,
    kToolGetHealth,
};

inline constexpr std::array<std::string_view, 4> kSupportedResources{
    kResourceStatusCurrent,
    kResourceReportsRecent,
    kResourceResultByTask,
    kResourceLogsByTask,
};

inline constexpr std::string_view to_string(McpEventKind kind) noexcept {
    switch (kind) {
    case McpEventKind::TaskStarted:
        return "task_started";
    case McpEventKind::TaskFinished:
        return "task_finished";
    case McpEventKind::WorkerStatus:
        return "worker_status";
    case McpEventKind::ConnectorDecision:
        return "connector_decision";
    case McpEventKind::Error:
        return "error";
    }
    return "error";
}

inline std::optional<McpEventKind> parse_event_kind(std::string_view value) noexcept {
    if (value == "task_started")
        return McpEventKind::TaskStarted;
    if (value == "task_finished")
        return McpEventKind::TaskFinished;
    if (value == "worker_status")
        return McpEventKind::WorkerStatus;
    if (value == "connector_decision")
        return McpEventKind::ConnectorDecision;
    if (value == "error")
        return McpEventKind::Error;
    return std::nullopt;
}

inline bool is_supported_tool(std::string_view tool_name) noexcept {
    for (const auto name : kSupportedTools) {
        if (name == tool_name)
            return true;
    }
    return false;
}

inline bool is_supported_resource(std::string_view resource_uri) noexcept {
    for (const auto uri : kSupportedResources) {
        if (uri == resource_uri)
            return true;
    }
    return false;
}

}  // namespace worker::mcp
