#include "worker/backend/HttpConnector.hpp"

namespace worker {

HttpConnector::HttpConnector(const WorkerConfig& config)
: config_(config) {}

fragment::ExecutionResult HttpConnector::execute(const BackendRequest&) {
    fragment::ExecutionResult result;
    result.success = false;
    if (config_.connector_endpoint.empty())
        result.error_message = "Connecteur HTTP non configuré (endpoint manquant)";
    else
        result.error_message = "Connecteur HTTP non implémenté (endpoint: " + config_.connector_endpoint + ")";
    return result;
}

}  // namespace worker
