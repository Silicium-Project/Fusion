#pragma once

#include <cstdint>
#include <string>

#include "worker/mcp/McpSchema.hpp"

namespace worker::mcp {

struct McpEnvelope {
    std::uint32_t schema_version = kMcpEnvelopeSchemaVersion;
    std::string event_id;
    std::string timestamp_utc;
    std::string source;
    McpEventKind kind = McpEventKind::Error;
    std::string task_id;
    std::string payload_json;
};

inline bool is_supported_schema_version(std::uint32_t schema_version) noexcept {
    return schema_version == kMcpEnvelopeSchemaVersion;
}

inline bool can_publish(const McpEnvelope& envelope) {
    if (!is_supported_schema_version(envelope.schema_version))
        return false;
    if (envelope.event_id.empty())
        return false;
    if (envelope.timestamp_utc.empty())
        return false;
    if (envelope.source.empty())
        return false;
    if (envelope.payload_json.empty())
        return false;
    return true;
}

}  // namespace worker::mcp
