#pragma once

#include "backend/ExecutionBackend.hpp"

namespace fragment {

// Backend d'exécution en mode émulation.
class EmulatedExecutionBackend : public IExecutionBackend {
public:
    bool run(const ExecutionEntry& entry,
             FragmentExecutor& executor,
             ExecutionResult& result) const override;
};

}  // namespace fragment

