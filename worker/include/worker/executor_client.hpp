#pragma once

#include <memory>
#include <string>

#include "ExecutionResult.hpp"
#include "FragmentApi.h"

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

    struct DllCloser {
        void operator()(void* handle) const;
    };

    struct ContextDeleter {
        DestroyFn fn = nullptr;
        void operator()(FE_Context* ctx) const;
    };

    std::unique_ptr<void, DllCloser> handle_;
    std::unique_ptr<FE_Context, ContextDeleter> context_{nullptr, ContextDeleter{}};
    RunFn run_ = nullptr;
    FreeResultFn free_result_ = nullptr;
};

}  // namespace worker
