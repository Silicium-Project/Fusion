#include "worker/backend/DirectConnector.hpp"

#include <iostream>

#include "worker/backend/DynamoBackend.hpp"
#include "worker/backend/LibraryBackend.hpp"

namespace worker {

DirectConnector::DirectConnector(const WorkerConfig& config)
: config_(config) {
    emulator_ = std::make_unique<LibraryBackend>(config_, config_.emulator_library, false, false);
    try {
        native_ = std::make_unique<LibraryBackend>(config_, config_.native_library, true, true);
    } catch (const std::exception& exc) {
        std::cerr << "[worker] Backend natif indisponible: " << exc.what()
                  << " (fallback emu uniquement si mode=auto)\n";
    }
    if (!config_.dynamo_runner_binary.empty())
        dynamo_ = std::make_unique<DynamoBackend>(config_);
}

DirectConnector::~DirectConnector() = default;

fragment::ExecutionResult DirectConnector::execute(const BackendRequest& request) {
    switch (config_.mode) {
        case ExecutionMode::Dynamo:
            if (dynamo_) return dynamo_->execute(request);
            throw std::runtime_error("Mode Dynamo requis mais runner indisponible");
        case ExecutionMode::Native:
            if (!native_)
                throw std::runtime_error("Backend natif indisponible");
            return native_->execute(request);
        case ExecutionMode::Emulator:
            return emulator_->execute(request);
        case ExecutionMode::Auto:
        default:
            if (dynamo_) return dynamo_->execute(request);
            if (native_) return native_->execute(request);
            std::cerr << "[worker] Backend natif indisponible, fallback emulation.\n";
            return emulator_->execute(request);
    }
}

}  // namespace worker
