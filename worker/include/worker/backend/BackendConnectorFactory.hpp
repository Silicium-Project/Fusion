#pragma once

#include <memory>

namespace worker {

class IBackendConnector;
class WorkerConfig;

class IBackendConnectorFactory {
public:
    virtual ~IBackendConnectorFactory() = default;
    virtual std::unique_ptr<IBackendConnector> create(const WorkerConfig& config) const = 0;
};

std::unique_ptr<IBackendConnectorFactory> make_backend_connector_factory();

}  // namespace worker
