#pragma once

#include <memory>
#include <string>

#include "worker/mcp/IMcpResourceStore.hpp"
#include "worker/mcp/IMcpToolRegistry.hpp"
#include "worker/mcp/McpSchema.hpp"

namespace worker::mcp {

struct McpToolRegistryConfig {
    bool enable_control_tools = false;
};

class McpGuardedToolRegistry : public IMcpToolRegistry {
public:
    explicit McpGuardedToolRegistry(std::shared_ptr<IMcpResourceStore> store,
                                    McpToolRegistryConfig config = {});

    std::string execute_tool(const std::string& tool_name, const std::string& args_json) override;

private:
    std::shared_ptr<IMcpResourceStore> store_;
    McpToolRegistryConfig config_{};
};

}  // namespace worker::mcp
