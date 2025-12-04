#pragma once

#include "fragment/cli.hpp"
#include "fragment/execution_result.hpp"
#include "fragment/fragment_executor.hpp"

namespace fragment {

class EmulatedRunner {
public:
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;
};

}  // namespace fragment
