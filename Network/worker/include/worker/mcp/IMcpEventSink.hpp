#pragma once

#include "worker/mcp/McpEnvelope.hpp"

namespace worker::mcp {

class IMcpEventSink {
public:
    virtual ~IMcpEventSink() = default;
    virtual void publish_event(const McpEnvelope& envelope) = 0;
};

}  // namespace worker::mcp
