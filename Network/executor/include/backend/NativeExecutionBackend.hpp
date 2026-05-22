#pragma once

#include "backend/ExecutionBackend.hpp"
#include "runtime/NativeRunner.hpp"

namespace fragment {

// Backend d'exécution en mode natif (sans repli implicite).
class NativeExecutionBackend : public IExecutionBackend {
public:
    explicit NativeExecutionBackend(bool force_native);

    bool run(const ExecutionEntry& entry,
             FragmentExecutor& executor,
             ExecutionResult& result) const override;

private:
    NativeRunner runner_;
};

}  // namespace fragment

