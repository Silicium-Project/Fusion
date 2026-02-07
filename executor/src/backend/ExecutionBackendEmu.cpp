#include "backend/ExecutionBackend.hpp"

#include "backend/EmulatedExecutionBackend.hpp"

namespace fragment {
namespace {

class EmulatedBackendFactory : public ExecutionBackendFactory {
public:
    std::unique_ptr<IExecutionBackend> create(bool /*native_mode*/,
                                              bool /*force_native*/) const override {
        return std::make_unique<EmulatedExecutionBackend>();
    }
};

}  // namespace

std::unique_ptr<ExecutionBackendFactory> make_backend_factory() {
    return std::make_unique<EmulatedBackendFactory>();
}

std::unique_ptr<IExecutionBackend> make_backend(bool native_mode, bool force_native) {
    return make_backend_factory()->create(native_mode, force_native);
}

}  // namespace fragment

