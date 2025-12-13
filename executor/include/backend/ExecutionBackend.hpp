#pragma once

#include <memory>

#include "Cli.hpp"
#include "FragmentExecutor.hpp"
#include "ExecutionResult.hpp"

namespace fragment {

// Interface minimaliste pour l'exécution d'un fragment.
class IExecutionBackend {
public:
    virtual ~IExecutionBackend() = default;
    virtual bool run(const ExecutionEntry& entry,
                     FragmentExecutor& executor,
                     ExecutionResult& result) const = 0;
};

// Fabrique un backend en fonction du mode demandé.
std::unique_ptr<IExecutionBackend> make_backend(bool native_mode, bool force_native);

}  // namespace fragment

