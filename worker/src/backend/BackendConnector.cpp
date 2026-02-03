#include "worker/backend/BackendConnector.hpp"

#include <stdexcept>

#include "worker/backend/DirectConnector.hpp"
#include "worker/backend/HttpConnector.hpp"

namespace worker {

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config) {
    switch (config.connector) {
        case ConnectorMode::Direct:
            return std::make_unique<DirectConnector>(config);
        case ConnectorMode::Http:
            return std::make_unique<HttpConnector>(config);
    }
    throw std::runtime_error("Connecteur inconnu");
}

}  // namespace worker
