#pragma once

#include <string>

namespace worker::mcp {

class IMcpToolRegistry {
public:
    virtual ~IMcpToolRegistry() = default;
    virtual std::string execute_tool(const std::string& tool_name, const std::string& args_json) = 0;
};

}  // namespace worker::mcp
