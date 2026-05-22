#pragma once

#include <string>

#include "worker/core/WorkerReport.hpp"
#include "worker/mcp/IMcpEventSink.hpp"
#include "worker/mcp/IMcpResourceStore.hpp"
#include "worker/mcp/IMcpToolRegistry.hpp"
#include "worker/task/TaskObserver.hpp"

namespace worker::mcp {

class IMcpConnectorAdapter : public ITaskObserver {
public:
    virtual ~IMcpConnectorAdapter() = default;
    virtual void publish_worker_report(const WorkerReport& report) = 0;
    virtual std::string read_resource(const std::string& resource_uri) const = 0;
    virtual std::string execute_tool(const std::string& tool_name, const std::string& args_json) = 0;
};

}  // namespace worker::mcp
