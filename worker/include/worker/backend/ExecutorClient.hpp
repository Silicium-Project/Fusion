#pragma once

#include <functional>
#include <memory>
#include <string>

#include "core/ExecutionResult.hpp"
#include "api/FragmentApi.h"

namespace worker {

struct BackendRequest;

class ExecutorClient {
public:
    explicit ExecutorClient(std::string library_path);
    fragment::ExecutionResult run(const BackendRequest& request,
                                  bool native_mode,
                                  bool force_native) const;

private:
    using CreateFn = FE_Context* (*)();
    using DestroyFn = void (*)(FE_Context*);
    using RunFn = int (*)(FE_Context*, const FE_Task*, FE_Result*);
    using FreeResultFn = void (*)(FE_Result*);
    using DllCloser = std::function<void(void*)>;
    using ContextDeleter = std::function<void(FE_Context*)>;

    std::unique_ptr<void, DllCloser> handle_;
    std::unique_ptr<FE_Context, ContextDeleter> context_{nullptr, ContextDeleter{}};
    RunFn run_ = nullptr;
    FreeResultFn free_result_ = nullptr;
};

}  // namespace worker
