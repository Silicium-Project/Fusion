#pragma once

#include "fragment/cli.hpp"
#include "fragment/emulated_runner.hpp"
#include "fragment/native_runner.hpp"

namespace fragment {

class ExecutionRouter {
public:
    ExecutionRouter(bool native_mode, bool force_native);
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;

private:
    bool native_mode_;
    EmulatedRunner emu_runner_;
    NativeRunner native_runner_;
};

}  // namespace fragment
