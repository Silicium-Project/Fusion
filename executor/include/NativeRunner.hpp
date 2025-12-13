#pragma once

#include "Cli.hpp"
#include "ExecutionResult.hpp"
#include "FragmentExecutor.hpp"

namespace fragment {

class NativeRunner {
public:
    explicit NativeRunner(bool force_native);
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;

private:
    bool force_native_;
};

}  // namespace fragment
