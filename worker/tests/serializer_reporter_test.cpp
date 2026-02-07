#include <gtest/gtest.h>

#include <sstream>

#include "worker/io/Reporter.hpp"
#include "worker/task/TaskSerializer.hpp"
#include "worker/core/WorkerReport.hpp"

namespace worker {

TEST(TaskSerializer, RoundTripPayload) {
    TaskPayload payload;
    payload.type = TaskType::Binary;
    payload.partition_id = "p1";
    payload.asm_path = "/tmp/a.asm";
    payload.binary_path = "/tmp/bin";
    payload.mode = ExecutionMode::Native;
    payload.inputs = {{"rax", 0x11}, {"rbx", 0x22}};
    payload.register_state = {{"rcx", 0x33}};
    MemorySnapshot snapshot;
    snapshot.address = 0x1000;
    snapshot.bytes = {0xaa, 0xbb};
    payload.memory_state = {snapshot};
    fragment::FdRule rule;
    rule.fd = 3;
    rule.capture = true;
    rule.alias = "log";
    rule.input_data = std::string("\xca\xfe", 2);
    payload.fd_rules.push_back(rule);

    const std::string serialized = serialize_task_payload(payload);
    EXPECT_NE(std::string::npos, serialized.find("\"schema_version\":1"));
    const TaskPayload deserialized = deserialize_task_payload(serialized);

    EXPECT_EQ(1u, deserialized.schema_version);
    EXPECT_EQ(payload.type, deserialized.type);
    EXPECT_EQ(payload.partition_id, deserialized.partition_id);
    EXPECT_EQ(payload.asm_path, deserialized.asm_path);
    EXPECT_EQ(payload.binary_path, deserialized.binary_path);
    EXPECT_EQ(payload.mode, deserialized.mode);
    EXPECT_EQ(payload.inputs, deserialized.inputs);
    EXPECT_EQ(payload.register_state, deserialized.register_state);
    ASSERT_EQ(payload.memory_state.size(), deserialized.memory_state.size());
    EXPECT_EQ(payload.memory_state[0].address, deserialized.memory_state[0].address);
    EXPECT_EQ(payload.memory_state[0].bytes, deserialized.memory_state[0].bytes);
    ASSERT_EQ(payload.fd_rules.size(), deserialized.fd_rules.size());
    EXPECT_EQ(payload.fd_rules[0].fd, deserialized.fd_rules[0].fd);
    EXPECT_EQ(payload.fd_rules[0].capture, deserialized.fd_rules[0].capture);
    EXPECT_EQ(payload.fd_rules[0].alias, deserialized.fd_rules[0].alias);
    EXPECT_EQ(payload.fd_rules[0].input_data, deserialized.fd_rules[0].input_data);
}

TEST(TaskSerializer, DefaultTypeWhenMissing) {
    const std::string json = R"({
      "partition_id":"p",
      "asm_path":"/tmp/a",
      "binary_path":"",
      "mode":"emu",
      "fd_redirections":[],
      "inputs":[],
      "register_state":[],
      "memory":[]
    })";
    TaskPayload payload = deserialize_task_payload(json);
    EXPECT_EQ(payload.type, TaskType::Binary);
}

TEST(TaskSerializer, RejectsUnknownType) {
    const std::string json = R"({
      "type":"mystery",
      "partition_id":"p",
      "asm_path":"/tmp/a",
      "binary_path":"",
      "mode":"emu",
      "fd_redirections":[],
      "inputs":[],
      "register_state":[],
      "memory":[]
    })";
    EXPECT_THROW(deserialize_task_payload(json), std::runtime_error);
}

TEST(TaskSerializer, RoundTripExecutionResult) {
    fragment::ExecutionResult result;
    result.success = true;
    result.error_message = "minor issue\n";
    result.program_stdout = "OUT\n";
    result.program_stderr = "ERR";
    result.instructions_executed = 42;
    result.memory_accesses = 7;
    result.initial_regs = {{"rax", 1}};
    result.final_regs = {{"rax", 2}};
    fragment::MemoryPatch patch;
    patch.address = 0x2000;
    patch.after = {0x01, 0x02, 0x03};
    result.memory_patches.push_back(patch);
    fragment::FdCapture cap1;
    cap1.data = "abc";
    fragment::FdCapture cap2;
    cap2.data = "xyz";
    cap2.alias = "stderr";
    result.fd_outputs.set(1, cap1);
    result.fd_outputs.set(2, cap2);

    const std::string serialized = serialize_execution_result(result);
    EXPECT_NE(std::string::npos, serialized.find("\"schema_version\":1"));
    const fragment::ExecutionResult deserialized = deserialize_execution_result(serialized);

    EXPECT_TRUE(deserialized.success);
    EXPECT_EQ(result.error_message, deserialized.error_message);
    EXPECT_EQ(result.program_stdout, deserialized.program_stdout);
    EXPECT_EQ(result.program_stderr, deserialized.program_stderr);
    EXPECT_EQ(result.instructions_executed, deserialized.instructions_executed);
    EXPECT_EQ(result.memory_accesses, deserialized.memory_accesses);
    EXPECT_EQ(result.initial_regs, deserialized.initial_regs);
    EXPECT_EQ(result.final_regs, deserialized.final_regs);
    // changed_regs should be recomputed during deserialization.
    ASSERT_EQ(1u, deserialized.changed_regs.size());
    EXPECT_EQ(1u, deserialized.changed_regs.at("rax").first);
    EXPECT_EQ(2u, deserialized.changed_regs.at("rax").second);
    ASSERT_EQ(1u, deserialized.memory_patches.size());
    EXPECT_EQ(result.memory_patches[0].address, deserialized.memory_patches[0].address);
    EXPECT_EQ(result.memory_patches[0].after, deserialized.memory_patches[0].after);
    ASSERT_TRUE(deserialized.fd_outputs.contains(2));
    EXPECT_EQ("xyz", deserialized.fd_outputs.at(2).data);
    EXPECT_EQ("stderr", deserialized.fd_outputs.at(2).alias);
}

TEST(Reporter, EmitsJsonAndText) {
    WorkerReport report;
    report.summary_path = "/tmp/summary.json";
    report.mode = ExecutionMode::Emulator;

    TaskReport task;
    task.partition_id = "part-1";
    task.inputs = {{"r1", 10}, {"r2", 20}};
    task.result.success = false;
    task.result.error_message = "boom";
    task.telemetry.task_id = "task-1";
    task.telemetry.type = TaskType::Binary;
    task.telemetry.status = "failure";
    task.telemetry.duration_ms = 12;
    task.telemetry.linux_policy = "native";
    task.telemetry.windows_policy = "skip";
    task.telemetry.wsl_enabled = true;
    task.telemetry.wsl_decision = "enabled";
    task.result.instructions_executed = 3;
    task.result.memory_accesses = 4;
    task.result.program_stdout = "hello\n";
    task.result.program_stderr = "warn";
    task.result.changed_regs["r1"] = {1, 2};
    fragment::MemoryPatch patch;
    patch.address = 0x4000;
    patch.before = {0xaa, 0xbb};
    patch.after = {0x11, 0x22};
    task.result.memory_patches.push_back(patch);
    fragment::FdCapture cap;
    cap.data = "DATA";
    cap.alias = "out";
    task.result.fd_outputs.set(5, cap);
    report.tasks.push_back(task);

    std::ostringstream json_stream;
    Reporter json_reporter(OutputFormat::Json, json_stream);
    json_reporter.emit(report);
    const std::string json_out = json_stream.str();
    EXPECT_NE(std::string::npos, json_out.find("\"task_id\":\"task-1\""));
    EXPECT_NE(std::string::npos, json_out.find("\"type\":\"binary\""));
    EXPECT_NE(std::string::npos, json_out.find("\"status\":\"failure\""));
    EXPECT_NE(std::string::npos, json_out.find("\"duration_ms\":12"));
    EXPECT_NE(std::string::npos, json_out.find("\"linux_policy\":\"native\""));
    EXPECT_NE(std::string::npos, json_out.find("\"windows_policy\":\"skip\""));
    EXPECT_NE(std::string::npos, json_out.find("\"wsl_enabled\":true"));
    EXPECT_NE(std::string::npos, json_out.find("\"wsl_decision\":\"enabled\""));
    EXPECT_NE(std::string::npos, json_out.find("\"partition\":\"part-1\""));
    EXPECT_NE(std::string::npos, json_out.find("\"fd_outputs\":{\"5\""));
    EXPECT_NE(std::string::npos, json_out.find("\"alias\":\"out\""));
    EXPECT_NE(std::string::npos, json_out.find("\"changed_registers\""));
    EXPECT_NE(std::string::npos, json_out.find("\"memory_patches\""));

    std::ostringstream text_stream;
    Reporter text_reporter(OutputFormat::Text, text_stream);
    text_reporter.emit(report);
    const std::string text_out = text_stream.str();
    EXPECT_NE(std::string::npos, text_out.find("Task ID: task-1"));
    EXPECT_NE(std::string::npos, text_out.find("Type: binary"));
    EXPECT_NE(std::string::npos, text_out.find("Status: failure"));
    EXPECT_NE(std::string::npos, text_out.find("Durée: 12 ms"));
    EXPECT_NE(std::string::npos, text_out.find("Policy: linux=native windows=skip"));
    EXPECT_NE(std::string::npos, text_out.find("WSL: on (enabled)"));
    EXPECT_NE(std::string::npos, text_out.find("Partition: part-1"));
    EXPECT_NE(std::string::npos, text_out.find("ÉCHEC"));
    EXPECT_NE(std::string::npos, text_out.find("fd 5 (out)"));
    EXPECT_NE(std::string::npos, text_out.find("Écritures mémoire"));
    EXPECT_NE(std::string::npos, text_out.find("avant"));
    EXPECT_NE(std::string::npos, text_out.find("après"));
}

TEST(TaskSerializer, RejectsUnsupportedPayloadSchemaVersion) {
    const std::string json = R"({
      "schema_version":99,
      "partition_id":"p",
      "asm_path":"/tmp/a",
      "binary_path":"",
      "mode":"emu",
      "fd_redirections":[],
      "inputs":[],
      "register_state":[],
      "memory":[]
    })";
    EXPECT_THROW(deserialize_task_payload(json), std::runtime_error);
}

TEST(TaskSerializer, RejectsUnsupportedExecutionResultSchemaVersion) {
    const std::string json = R"({
      "schema_version":99,
      "success":true,
      "error":"",
      "stdout":"",
      "stderr":"",
      "fd_outputs":{},
      "initial_regs":[],
      "final_regs":[],
      "memory_patches":[],
      "instructions":1,
      "memory_accesses":1
    })";
    EXPECT_THROW(deserialize_execution_result(json), std::runtime_error);
}

TEST(Reporter, DefaultsTelemetryFields) {
    WorkerReport report;
    report.summary_path = "/tmp/summary.json";
    report.mode = ExecutionMode::Emulator;

    TaskReport task;
    task.partition_id = "part-2";
    task.result.success = true;
    report.tasks.push_back(task);

    std::ostringstream json_stream;
    Reporter json_reporter(OutputFormat::Json, json_stream);
    json_reporter.emit(report);
    const std::string json_out = json_stream.str();
    EXPECT_NE(std::string::npos, json_out.find("\"task_id\":\"part-2\""));
    EXPECT_NE(std::string::npos, json_out.find("\"type\":\"binary\""));
    EXPECT_NE(std::string::npos, json_out.find("\"status\":\"success\""));
    EXPECT_NE(std::string::npos, json_out.find("\"duration_ms\":0"));
    EXPECT_NE(std::string::npos, json_out.find("\"linux_policy\""));
    EXPECT_NE(std::string::npos, json_out.find("\"windows_policy\""));
    EXPECT_NE(std::string::npos, json_out.find("\"wsl_enabled\""));
    EXPECT_NE(std::string::npos, json_out.find("\"wsl_decision\""));
}

TEST(TaskSerializer, DeserializeTaskPayloadRejectsBadMemoryHex) {
    const std::string bad_json = R"({
      "partition_id":"p",
      "asm_path":"/tmp/a",
      "binary_path":"",
      "mode":"emu",
      "fd_redirections":[],
      "inputs":[],
      "register_state":[],
      "memory":["0x10:abc"]
    })";
    EXPECT_THROW(deserialize_task_payload(bad_json), std::runtime_error);
}

TEST(TaskSerializer, DeserializeResultRejectsBadPatch) {
    const std::string bad_json = R"({
      "success":true,
      "error":"",
      "stdout":"",
      "stderr":"",
      "fd_outputs":{},
      "initial_regs":[],
      "final_regs":[],
      "memory_patches":["0x1"],
      "instructions":1,
      "memory_accesses":1
    })";
    EXPECT_THROW(deserialize_execution_result(bad_json), std::runtime_error);
}

}  // namespace worker
