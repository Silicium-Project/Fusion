#include <memory>
#include <type_traits>
#include <utility>

#include <gtest/gtest.h>

#include "worker/backend/BackendConnector.hpp"
#include "worker/backend/BackendConnectorFactory.hpp"
#include "worker/core/WorkerConfig.hpp"
#include "worker/task/TaskHandlerFactory.hpp"
#include "worker/task/TaskObserver.hpp"

namespace {

using worker::BackendConnector;
using worker::BackendConnectorFactory;
using worker::IBackendConnector;
using worker::IBackendConnectorFactory;
using worker::ITaskHandlerFactory;
using worker::ITaskObserver;
using worker::TaskHandlerFactory;
using worker::TaskObserver;

using BackendConnectorReturn =
    decltype(worker::make_backend_connector(std::declval<const worker::WorkerConfig&>()));
using BackendConnectorFactoryReturn = decltype(worker::make_backend_connector_factory());
using TaskHandlerFactoryReturn = decltype(worker::make_task_handler_factory());

static_assert(std::is_same_v<BackendConnector, IBackendConnector>);
static_assert(std::is_same_v<BackendConnectorFactory, IBackendConnectorFactory>);
static_assert(std::is_same_v<TaskHandlerFactory, ITaskHandlerFactory>);
static_assert(std::is_same_v<TaskObserver, ITaskObserver>);
static_assert(std::is_same_v<BackendConnectorReturn, std::unique_ptr<IBackendConnector>>);
static_assert(std::is_same_v<BackendConnectorFactoryReturn, std::unique_ptr<IBackendConnectorFactory>>);
static_assert(std::is_same_v<TaskHandlerFactoryReturn, std::unique_ptr<ITaskHandlerFactory>>);

}  // namespace

TEST(WorkerInterfaceCompat, LegacyAliasesRemainAssignable) {
    std::shared_ptr<ITaskObserver> modern;
    std::shared_ptr<TaskObserver> legacy = modern;
    EXPECT_EQ(legacy, modern);
}
