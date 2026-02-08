#include <gtest/gtest.h>

#include "worker/backend/BackendConnector.hpp"
#include "worker/core/Worker.hpp"

namespace worker {
namespace {

class FakeConnector : public BackendConnector {
public:
    fragment::ExecutionResult execute(const BackendRequest&) override {
        called = true;
        fragment::ExecutionResult result;
        result.success = true;
        return result;
    }

    bool called = false;
};

Task make_task() {
    Task task;
    task.type = TaskType::Binary;
    task.partition_id = "p1";
    return task;
}

fragment::PartitionInfo make_partition(const std::string& os) {
    fragment::PartitionInfo partition;
    partition.id = "p1";
    partition.os = os;
    return partition;
}

}  // namespace

TEST(OsPolicyRouting, SkipLinuxFragment) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Skip;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("ignore"));
    EXPECT_EQ("policy_skip", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, ErrorLinuxFragment) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Error;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("refuse"));
    EXPECT_EQ("policy_error", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, QueueLinuxFragment) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Queue;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("file"));
    EXPECT_EQ("policy_queue", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, NativeLinuxFragment) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Native;
    config.capabilities.native = true;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_TRUE(report.result.success);
    EXPECT_EQ("native", report.telemetry.required_backend);
    EXPECT_EQ("policy_native_execute", report.telemetry.routing_decision);
    EXPECT_TRUE(connector_ptr->called);
}

TEST(OsPolicyRouting, WslLinuxFragmentRequiresTrigger) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Wsl;
    config.wsl_enabled = false;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("WSL"));
    EXPECT_EQ("policy_wsl_triggers_disabled", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, WslLinuxFragmentAllowed) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Wsl;
    config.wsl_enabled = true;
    config.capabilities.wsl = true;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_TRUE(report.result.success);
    EXPECT_EQ("wsl", report.telemetry.required_backend);
    EXPECT_EQ("policy_wsl_execute", report.telemetry.routing_decision);
    EXPECT_TRUE(connector_ptr->called);
}

TEST(OsPolicyRouting, WindowsPolicyIsUsed) {
    WorkerConfig config;
    config.fragment_os_policy.windows = FragmentOsAction::Skip;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("windows"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_EQ("policy_skip", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, NativePolicyFailsWhenNativeCapabilityDisabled) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Native;
    config.capabilities.native = false;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("Backend non supporte"));
    EXPECT_EQ("native", report.telemetry.required_backend);
    EXPECT_EQ("policy_native_unsupported", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, WslPolicyFailsWhenWslCapabilityDisabled) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Wsl;
    config.wsl_enabled = true;
    config.capabilities.wsl = false;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_NE(std::string::npos, report.result.error_message.find("Backend non supporte"));
    EXPECT_EQ("wsl", report.telemetry.required_backend);
    EXPECT_EQ("policy_wsl_unsupported", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

TEST(OsPolicyRouting, NativePolicyUsesHttpCapabilityWhenHttpConnectorIsSelected) {
    WorkerConfig config;
    config.fragment_os_policy.linux = FragmentOsAction::Native;
    config.connector = ConnectorMode::Http;
    config.capabilities.http = false;
    auto connector = std::make_unique<FakeConnector>();
    auto* connector_ptr = connector.get();
    Worker worker(config, std::move(connector));

    auto report = worker.run_task(make_partition("linux"), "", "", "", make_task());
    EXPECT_FALSE(report.result.success);
    EXPECT_EQ("http", report.telemetry.required_backend);
    EXPECT_EQ("policy_native_unsupported", report.telemetry.routing_decision);
    EXPECT_FALSE(connector_ptr->called);
}

}  // namespace worker
