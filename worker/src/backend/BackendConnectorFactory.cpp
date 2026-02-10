#include "worker/backend/BackendConnectorFactory.hpp"

#include <stdexcept>

#include "worker/backend/BackendConnector.hpp"
#include "worker/backend/DirectConnector.hpp"
#include "worker/backend/HttpConnector.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {
namespace {

class DefaultBackendConnectorFactory : public IBackendConnectorFactory {
public:
    std::unique_ptr<IBackendConnector> create(const WorkerConfig& config) const override {
        switch (config.connector) {
            case ConnectorMode::Direct:
                return std::make_unique<DirectConnector>(config);
            case ConnectorMode::Http:
                return std::make_unique<HttpConnector>(config);
        }
        throw std::runtime_error("Connecteur inconnu");
    }
};

}  // namespace

std::unique_ptr<IBackendConnectorFactory> make_backend_connector_factory() {
    return std::make_unique<DefaultBackendConnectorFactory>();
}

}  // namespace worker
