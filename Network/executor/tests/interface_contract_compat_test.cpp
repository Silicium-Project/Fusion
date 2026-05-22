#include <memory>
#include <string>
#include <type_traits>
#include <utility>

#include <gtest/gtest.h>

#include "backend/ExecutionBackend.hpp"
#include "support/Hash.hpp"

namespace {

using fragment::ExecutionBackendFactory;
using fragment::Hasher;
using fragment::IExecutionBackendFactory;
using fragment::IHasher;

using BackendFactoryReturn = decltype(fragment::make_backend_factory());

static_assert(std::is_same_v<ExecutionBackendFactory, IExecutionBackendFactory>);
static_assert(std::is_same_v<Hasher, IHasher>);
static_assert(std::is_same_v<BackendFactoryReturn, std::unique_ptr<IExecutionBackendFactory>>);

}  // namespace

TEST(ExecutorInterfaceCompat, LegacyAliasesRemainAssignable) {
    EXPECT_TRUE((std::is_same_v<Hasher, IHasher>));
}
