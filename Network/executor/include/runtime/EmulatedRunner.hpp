#pragma once

#include "cli/Cli.hpp"
#include "core/ExecutionResult.hpp"
#include "core/FragmentExecutor.hpp"

namespace fragment {

class EmulatedRunner {
public:
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;
};

}  // namespace fragment
