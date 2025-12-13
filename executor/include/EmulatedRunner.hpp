#pragma once

#include "Cli.hpp"
#include "ExecutionResult.hpp"
#include "FragmentExecutor.hpp"

namespace fragment {

class EmulatedRunner {
public:
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;
};

}  // namespace fragment
