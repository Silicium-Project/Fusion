#pragma once

#include <memory>

namespace worker {

class BackendConnector;
class WorkerConfig;

class BackendConnectorFactory {
public:
    virtual ~BackendConnectorFactory() = default;
    virtual std::unique_ptr<BackendConnector> create(const WorkerConfig& config) const = 0;
};

std::unique_ptr<BackendConnectorFactory> make_backend_connector_factory();

}  // namespace worker
