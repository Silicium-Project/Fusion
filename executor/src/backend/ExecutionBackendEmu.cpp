#include "backend/ExecutionBackend.hpp"

#include "backend/EmulatedExecutionBackend.hpp"

namespace fragment {

std::unique_ptr<IExecutionBackend> make_backend(bool /*native_mode*/, bool /*force_native*/) {
    return std::make_unique<EmulatedExecutionBackend>();
}

}  // namespace fragment

