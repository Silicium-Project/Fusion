#include "worker/backend/BackendConnector.hpp"

#include "worker/backend/BackendConnectorFactory.hpp"

namespace worker {

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config) {
    return make_backend_connector_factory()->create(config);
}

}  // namespace worker
