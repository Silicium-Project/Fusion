#include "backend/EmulatedExecutionBackend.hpp"

#include "runtime/EmulatedRunner.hpp"

namespace fragment {

bool EmulatedExecutionBackend::run(const ExecutionEntry& entry,
                                   FragmentExecutor& executor,
                                   ExecutionResult& result) const {
    EmulatedRunner runner;
    return runner.run(entry, executor, result);
}

}  // namespace fragment
