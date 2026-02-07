#pragma once

#include <atomic>
#include <memory>
#include <string>

#include "worker/mcp/IMcpConnectorAdapter.hpp"
#include "worker/mcp/McpGuardedToolRegistry.hpp"

namespace worker::mcp {

struct McpReadOnlyAdapterOptions {
    bool enable_control_tools = false;
};

using McpAdapterMetrics = McpToolMetrics;

class McpReadOnlyConnectorAdapter : public IMcpConnectorAdapter {
public:
    McpReadOnlyConnectorAdapter();
    explicit McpReadOnlyConnectorAdapter(std::shared_ptr<IMcpResourceStore> store);
    McpReadOnlyConnectorAdapter(std::shared_ptr<IMcpResourceStore> store,
                                std::shared_ptr<IMcpEventSink> event_sink,
                                McpReadOnlyAdapterOptions options = {});

    void on_task_start(const TaskContext& context, const Task& task) override;
    void on_task_finish(const TaskContext& context, const Task& task, const TaskReport& report) override;
    void publish_worker_report(const WorkerReport& report) override;
    std::string read_resource(const std::string& resource_uri) const override;
    std::string execute_tool(const std::string& tool_name, const std::string& args_json) override;
    McpAdapterMetrics snapshot_metrics() const;

private:
    std::shared_ptr<IMcpResourceStore> store_;
    std::shared_ptr<IMcpEventSink> event_sink_;
    std::shared_ptr<IMcpToolRegistry> tool_registry_;
    std::shared_ptr<McpGuardedToolRegistry> guarded_tool_registry_;
    std::atomic<std::uint64_t> sequence_{0};

    void publish_event(McpEnvelope envelope);
};

}  // namespace worker::mcp
