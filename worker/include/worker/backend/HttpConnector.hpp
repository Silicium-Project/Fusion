#pragma once

#include "worker/backend/BackendConnector.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class HttpConnector : public BackendConnector {
public:
    explicit HttpConnector(const WorkerConfig& config);

    fragment::ExecutionResult execute(const BackendRequest& request) override;

private:
    const WorkerConfig& config_;
};

}  // namespace worker
