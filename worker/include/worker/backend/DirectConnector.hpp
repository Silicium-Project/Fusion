#pragma once

#include <memory>

#include "worker/backend/BackendConnector.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class DynamoBackend;
class LibraryBackend;

class DirectConnector : public BackendConnector {
public:
    explicit DirectConnector(const WorkerConfig& config);
    ~DirectConnector() override;

    fragment::ExecutionResult execute(const BackendRequest& request) override;

private:
    const WorkerConfig& config_;
    std::unique_ptr<LibraryBackend> emulator_;
    std::unique_ptr<LibraryBackend> native_;
    std::unique_ptr<DynamoBackend> dynamo_;
};

}  // namespace worker
