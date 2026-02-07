#pragma once

#include <cstdint>
#include <mutex>
#include <memory>
#include <string>

#include "worker/mcp/IMcpResourceStore.hpp"
#include "worker/mcp/IMcpToolRegistry.hpp"
#include "worker/mcp/McpSchema.hpp"

namespace worker::mcp {

struct McpToolRegistryConfig {
    bool enable_control_tools = false;
};

struct McpToolMetrics {
    std::uint64_t calls = 0;
    std::uint64_t failures = 0;
    std::uint64_t last_latency_ms = 0;
    std::string last_error;
};

class McpGuardedToolRegistry : public IMcpToolRegistry {
public:
    explicit McpGuardedToolRegistry(std::shared_ptr<IMcpResourceStore> store,
                                    McpToolRegistryConfig config = {});

    std::string execute_tool(const std::string& tool_name, const std::string& args_json) override;
    McpToolMetrics snapshot_metrics() const;

private:
    std::shared_ptr<IMcpResourceStore> store_;
    McpToolRegistryConfig config_{};
    mutable std::mutex metrics_mutex_;
    McpToolMetrics metrics_{};
};

}  // namespace worker::mcp
