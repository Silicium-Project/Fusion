#include "worker/mcp/McpGuardedToolRegistry.hpp"

#include <sstream>

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

}  // namespace

McpGuardedToolRegistry::McpGuardedToolRegistry(std::shared_ptr<IMcpResourceStore> store,
                                               McpToolRegistryConfig config)
: store_(std::move(store)),
  config_(config) {}

std::string McpGuardedToolRegistry::execute_tool(const std::string& tool_name,
                                                 const std::string& args_json) {
    if (!is_supported_tool(tool_name))
        return tool_error_json("unsupported_tool", tool_name, "tool is not supported");

    if (tool_name == std::string(kToolGetHealth)) {
        if (!store_)
            return tool_error_json("store_unavailable", tool_name, "resource store is unavailable");
        return store_->read_resource(std::string(kResourceStatusCurrent));
    }

    if (!config_.enable_control_tools)
        return tool_error_json("tool_disabled", tool_name, "control tools are disabled by policy");

    std::ostringstream oss;
    oss << "{"
        << "\"schema_version\":" << kMcpEnvelopeSchemaVersion << ","
        << "\"tool\":\"" << escape_json(tool_name) << "\","
        << "\"accepted\":false,"
        << "\"status\":\"not_implemented\","
        << "\"message\":\"control path is enabled but not wired yet\","
        << "\"args_json\":\"" << escape_json(args_json) << "\""
        << "}";
    return oss.str();
}

}  // namespace worker::mcp
