#include "runtime/EmulatedRunner.hpp"

namespace fragment {

bool EmulatedRunner::run(const ExecutionEntry& entry,
                         FragmentExecutor& executor,
                         ExecutionResult& result) const {
    result = executor.execute_safe(entry.asm_path);
    return true;
}

}  // namespace fragment
