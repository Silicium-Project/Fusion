#pragma once

#include <memory>

#include "cli/Cli.hpp"
#include "core/FragmentExecutor.hpp"
#include "core/ExecutionResult.hpp"

namespace fragment {

// Interface minimaliste pour l'exécution d'un fragment.
class IExecutionBackend {
public:
    virtual ~IExecutionBackend() = default;
    virtual bool run(const ExecutionEntry& entry,
                     FragmentExecutor& executor,
                     ExecutionResult& result) const = 0;
};

class IExecutionBackendFactory {
public:
    virtual ~IExecutionBackendFactory() = default;
    virtual std::unique_ptr<IExecutionBackend> create(bool native_mode,
                                                      bool force_native) const = 0;
};

using ExecutionBackendFactory = IExecutionBackendFactory;

// Fabrique un backend en fonction du mode demandé.
std::unique_ptr<IExecutionBackendFactory> make_backend_factory();

// Fabrique un backend en fonction du mode demandé.
std::unique_ptr<IExecutionBackend> make_backend(bool native_mode, bool force_native);

}  // namespace fragment

