#include <gtest/gtest.h>

#include "core/ExecutionResult.hpp"
#include "partition/PartitionSummary.hpp"
#include "worker/backend/BackendConnector.hpp"
#include "worker/core/Worker.hpp"

namespace {

class FakeConnector : public worker::BackendConnector {
public:
    fragment::ExecutionResult result;
    std::vector<std::vector<worker::MemorySnapshot>> memory_states;
    std::vector<worker::RegisterState> register_states;

    fragment::ExecutionResult execute(const worker::BackendRequest& request) override {
        memory_states.push_back(request.memory_state);
        register_states.push_back(request.register_state);
        return result;
    }
};

fragment::PartitionInfo make_partition(std::string id) {
    fragment::PartitionInfo info;
    info.id = std::move(id);
    return info;
}

}  // namespace

TEST(WorkerState, ResetsBetweenTasksWhenEnabled) {
    worker::WorkerConfig config;
    config.reset_between_tasks = true;
    auto fake = std::make_unique<FakeConnector>();
    fake->result.success = true;
    fake->result.final_regs = {{"rax", 7}};
    fake->result.memory_patches.push_back({0x4000, {}, {0xDE, 0xAD}});
    FakeConnector* fake_ptr = fake.get();

    worker::Worker worker(config, std::move(fake));
    worker::MemorySnapshot snap;
    snap.address = 0x1000;
    snap.bytes = {0xAA};
    worker.load_initial_memory({snap});

    worker::Task task;
    task.partition_id = "p1";
    auto partition = make_partition("p1");
    worker.run_task(partition, "asm", "bin", "summary", task);
    worker.run_task(partition, "asm", "bin", "summary", task);

    ASSERT_EQ(2u, fake_ptr->memory_states.size());
    for (const auto& mem_state : fake_ptr->memory_states) {
        ASSERT_EQ(1u, mem_state.size());
        EXPECT_EQ(0x1000u, mem_state[0].address);
        EXPECT_EQ(snap.bytes, mem_state[0].bytes);
    }
    ASSERT_EQ(2u, fake_ptr->register_states.size());
    EXPECT_TRUE(fake_ptr->register_states[0].empty());
    EXPECT_TRUE(fake_ptr->register_states[1].empty());
}

TEST(WorkerState, KeepsStateWhenResetDisabled) {
    worker::WorkerConfig config;
    config.reset_between_tasks = false;
    auto fake = std::make_unique<FakeConnector>();
    fake->result.success = true;
    fake->result.final_regs = {{"rbx", 5}};
    fake->result.memory_patches.push_back({0x5000, {}, {0x01, 0x02}});
    FakeConnector* fake_ptr = fake.get();

    worker::Worker worker(config, std::move(fake));
    worker::MemorySnapshot snap;
    snap.address = 0x2000;
    snap.bytes = {0x10};
    worker.load_initial_memory({snap});

    worker::Task task;
    task.partition_id = "p2";
    auto partition = make_partition("p2");

    worker.run_task(partition, "asm", "bin", "summary", task);
    worker.run_task(partition, "asm", "bin", "summary", task);

    ASSERT_EQ(2u, fake_ptr->memory_states.size());
    const auto& first_state = fake_ptr->memory_states[0];
    ASSERT_EQ(1u, first_state.size());
    EXPECT_EQ(0x2000u, first_state[0].address);
    EXPECT_EQ(snap.bytes, first_state[0].bytes);

    const auto& second_state = fake_ptr->memory_states[1];
    ASSERT_EQ(2u, second_state.size());
    EXPECT_EQ(0x2000u, second_state[0].address);
    EXPECT_EQ(0x10u, second_state[0].bytes[0]);
    EXPECT_EQ(0x5000u, second_state[1].address);
    EXPECT_EQ((std::vector<uint8_t>{0x01, 0x02}), second_state[1].bytes);

    ASSERT_EQ(2u, fake_ptr->register_states.size());
    EXPECT_TRUE(fake_ptr->register_states[0].empty());
    ASSERT_EQ(1u, fake_ptr->register_states[1].size());
    EXPECT_EQ(5u, fake_ptr->register_states[1].at("rbx"));
}
