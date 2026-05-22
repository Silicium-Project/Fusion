#pragma once

#include <memory>
#include <string>

#include "core/ExecutionResult.hpp"

#include "worker/backend/BackendRequest.hpp"
#include "worker/backend/ExecutorClient.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class LibraryBackend {
public:
    LibraryBackend(const WorkerConfig& config,
                   std::string library_path,
                   bool native_mode,
                   bool force_native);

    fragment::ExecutionResult execute(const BackendRequest& request);

private:
    std::unique_ptr<ExecutorClient> client_;
    bool native_mode_;
    bool force_native_;
};

}  // namespace worker
