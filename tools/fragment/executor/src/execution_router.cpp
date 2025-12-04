#include "fragment/execution_router.hpp"

namespace fragment {

ExecutionRouter::ExecutionRouter(bool native_mode, bool force_native)
    : native_mode_(native_mode),
      emu_runner_(),
      native_runner_(force_native) {}

bool ExecutionRouter::run(const ExecutionEntry& entry,
                          FragmentExecutor& executor,
                          ExecutionResult& result) const {
    if (!native_mode_)
        return emu_runner_.run(entry, executor, result);

    if (native_runner_.run(entry, executor, result))
        return true;
    return emu_runner_.run(entry, executor, result);
}

}  // namespace fragment
