#pragma once

#include <string>

#include "worker/mcp/McpEnvelope.hpp"

namespace worker::mcp {

class IMcpResourceStore {
public:
    virtual ~IMcpResourceStore() = default;
    virtual void upsert_from_event(const McpEnvelope& envelope) = 0;
    virtual std::string read_resource(const std::string& resource_uri) const = 0;
};

}  // namespace worker::mcp
