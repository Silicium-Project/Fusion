#pragma once

#include <cstddef>
#include <deque>
#include <mutex>
#include <string>
#include <unordered_map>

#include "worker/mcp/IMcpResourceStore.hpp"

namespace worker::mcp {

class InMemoryMcpResourceStore : public IMcpResourceStore {
public:
    explicit InMemoryMcpResourceStore(std::size_t max_recent_events = 64);

    void upsert_from_event(const McpEnvelope& envelope) override;
    std::string read_resource(const std::string& resource_uri) const override;

private:
    std::size_t max_recent_events_;
    mutable std::mutex mutex_;
    std::string current_status_json_;
    std::deque<std::string> recent_event_envelopes_;
    std::unordered_map<std::string, std::string> task_result_payloads_;
    std::unordered_map<std::string, std::string> task_log_payloads_;
};

}  // namespace worker::mcp
