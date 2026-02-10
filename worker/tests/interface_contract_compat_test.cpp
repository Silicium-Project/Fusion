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

using worker::IBackendConnector;
using worker::IBackendConnectorFactory;
using worker::ITaskHandlerFactory;
using worker::ITaskObserver;

using BackendConnectorReturn =
    decltype(worker::make_backend_connector(std::declval<const worker::WorkerConfig&>()));
using BackendConnectorFactoryReturn = decltype(worker::make_backend_connector_factory());
using TaskHandlerFactoryReturn = decltype(worker::make_task_handler_factory());

static_assert(std::is_same_v<BackendConnectorReturn, std::unique_ptr<IBackendConnector>>);
static_assert(std::is_same_v<BackendConnectorFactoryReturn, std::unique_ptr<IBackendConnectorFactory>>);
static_assert(std::is_same_v<TaskHandlerFactoryReturn, std::unique_ptr<ITaskHandlerFactory>>);
static_assert(std::is_abstract_v<IBackendConnector>);
static_assert(std::is_abstract_v<IBackendConnectorFactory>);
static_assert(std::is_abstract_v<ITaskHandlerFactory>);
static_assert(std::is_abstract_v<ITaskObserver>);

}  // namespace

TEST(WorkerInterfaceCompat, InterfaceContractsRemainAbstract) {
    EXPECT_TRUE((std::is_abstract_v<IBackendConnector>));
    EXPECT_TRUE((std::is_abstract_v<IBackendConnectorFactory>));
    EXPECT_TRUE((std::is_abstract_v<ITaskHandlerFactory>));
    EXPECT_TRUE((std::is_abstract_v<ITaskObserver>));
}
