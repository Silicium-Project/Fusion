#pragma once

#include "fragment/cli.hpp"
#include "fragment/execution_result.hpp"
#include "fragment/fragment_executor.hpp"

namespace fragment {

class NativeRunner {
public:
    explicit NativeRunner(bool force_native);
    bool run(const ExecutionEntry& entry, FragmentExecutor& executor, ExecutionResult& result) const;

private:
    bool force_native_;
};

}  // namespace fragment
