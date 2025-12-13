#include "backend/ExecutionBackend.hpp"

#include "backend/NativeExecutionBackend.hpp"

namespace fragment {

std::unique_ptr<IExecutionBackend> make_backend(bool /*native_mode*/, bool force_native) {
    return std::make_unique<NativeExecutionBackend>(force_native);
}

}  // namespace fragment
