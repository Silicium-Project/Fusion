#include "worker/backend/LibraryBackend.hpp"

#include <stdexcept>

namespace worker {

LibraryBackend::LibraryBackend(const WorkerConfig& config,
                               std::string library_path,
                               bool native_mode,
                               bool force_native)
: client_(std::make_unique<ExecutorClient>(std::move(library_path)))
, native_mode_(native_mode)
, force_native_(force_native) {
    (void)config;
}

fragment::ExecutionResult LibraryBackend::execute(const BackendRequest& request) {
    if (!client_)
        throw std::runtime_error("Backend d'exÃ©cution indisponible");
    return client_->run(request, native_mode_, force_native_);
}

}  // namespace worker
