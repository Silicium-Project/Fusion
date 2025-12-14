#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "PartitionSummary.hpp"
#include "worker/backend_connector.hpp"
#include "worker/dynamorio_runner.hpp"

namespace worker {
namespace {

std::filesystem::path make_tmp_dir(const std::string& name) {
    auto base = std::filesystem::current_path() / "build" / "test_tmp" / name;
    std::filesystem::create_directories(base);
    return base;
}

std::filesystem::path write_script(const std::filesystem::path& dir, const std::string& name, const std::string& body) {
    auto path = dir / name;
    std::ofstream file(path);
    file << body;
    file.close();
    std::filesystem::permissions(path,
                                 std::filesystem::perms::owner_exec | std::filesystem::perms::owner_read
                                     | std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::add);
    return path;
}

}  // namespace

TEST(DynamoRunner, RunBinarySuccess) {
    auto tmp = make_tmp_dir("runner_success");
    auto launcher = write_script(tmp, "launcher.sh",
                                 "#!/bin/sh\n"
                                 "echo \"LAUNCH:$@\"\n"
                                 "exit 0\n");
    auto dummy_bin = tmp / "dummy.bin";
    std::ofstream(dummy_bin) << "bin";

    DynamoRunner runner(launcher.string());
    std::string out;
    std::string err;
    const bool ok = runner.run_binary(dummy_bin.string(), {"--foo", "bar"}, out, err);
    EXPECT_TRUE(ok);
    EXPECT_NE(std::string::npos, out.find("dummy.bin"));
    EXPECT_EQ("", err);
}

TEST(DynamoRunner, RunBinaryFailureSetsError) {
    auto tmp = make_tmp_dir("runner_fail");
    auto launcher = write_script(tmp, "launcher.sh",
                                 "#!/bin/sh\n"
                                 "exit 7\n");
    auto dummy_bin = tmp / "dummy.bin";
    std::ofstream(dummy_bin) << "bin";

    DynamoRunner runner(launcher.string());
    std::string out;
    std::string err;
    const bool ok = runner.run_binary(dummy_bin.string(), {}, out, err);
    EXPECT_FALSE(ok);
    EXPECT_TRUE(err.find("7") != std::string::npos);
}

TEST(BackendConnector, DynamoBackendExecutesAndParsesOutput) {
    auto tmp = make_tmp_dir("backend_dynamo");
    // Script that writes the output JSON where requested.
    auto runner_bin = write_script(tmp, "runner.sh",
                                   "#!/bin/sh\n"
                                   "out=\"\"\n"
                                   "while [ \"$#\" -gt 0 ]; do\n"
                                   "  if [ \"$1\" = \"--output\" ]; then out=\"$2\"; shift 2; continue; fi\n"
                                   "  shift\n"
                                   "done\n"
                                   "echo \"dyn_stdout\"\n"
                                   "cat >\"$out\" <<'EOF'\n"
                                   "{\n"
                                   "  \"success\":true,\n"
                                   "  \"error\":\"\",\n"
                                   "  \"stdout\":\"X\",\n"
                                   "  \"stderr\":\"\",\n"
                                   "  \"fd_outputs\":{},\n"
                                   "  \"initial_regs\":[\"rax=0x1\"],\n"
                                   "  \"final_regs\":[\"rax=0x2\"],\n"
                                   "  \"memory_patches\":[],\n"
                                   "  \"instructions\":5,\n"
                                   "  \"memory_accesses\":3\n"
                                   "}\n"
                                   "EOF\n"
                                   "exit 0\n");

    WorkerConfig config;
    config.mode = ExecutionMode::Dynamo;
    config.dynamo_launcher = "/bin/sh";
    config.dynamo_runner_binary = runner_bin.string();
    fragment::PartitionInfo part;
    part.id = "p1";
    BackendRequest request{part,
                           tmp.string(),
                           (tmp / "prog.asm").string(),
                           (tmp / "prog.bin").string(),
                           {{"rax", 0}},
                           {{"rax", 0}},
                           {},
                           {}};

    auto connector = make_backend_connector(config);
    fragment::ExecutionResult result = connector->execute(request);

    EXPECT_TRUE(result.success);
    EXPECT_EQ("X", result.program_stdout);
    EXPECT_EQ(5u, result.instructions_executed);
    ASSERT_TRUE(result.changed_regs.find("rax") != result.changed_regs.end());
    EXPECT_EQ(1u, result.changed_regs["rax"].first);
    EXPECT_EQ(2u, result.changed_regs["rax"].second);
}

TEST(BackendConnector, HttpConnectorMessages) {
    WorkerConfig config;
    config.connector = ConnectorMode::Http;
    config.connector_endpoint.clear();
    fragment::PartitionInfo part;
    part.id = "p1";
    auto connector = make_backend_connector(config);
    BackendRequest req{part, "", "", "", {}, {}, {}, {}};
    fragment::ExecutionResult res = connector->execute(req);
    EXPECT_FALSE(res.success);
    EXPECT_NE(std::string::npos, res.error_message.find("endpoint manquant"));

    config.connector_endpoint = "http://example";
    connector = make_backend_connector(config);
    res = connector->execute(req);
    EXPECT_FALSE(res.success);
    EXPECT_NE(std::string::npos, res.error_message.find("non implémenté"));
}

TEST(BackendConnector, DynamoBackendMissingBinaryThrows) {
    WorkerConfig config;
    config.mode = ExecutionMode::Dynamo;
    config.dynamo_launcher = "/bin/sh";
    config.dynamo_runner_binary = "/tmp/definitely_missing_runner.sh";
    EXPECT_THROW(make_backend_connector(config), std::runtime_error);
}

TEST(BackendConnector, DynamoBackendBadJsonSetsError) {
    auto tmp = make_tmp_dir("backend_bad_json");
    auto runner_bin = write_script(tmp, "runner.sh",
                                   "#!/bin/sh\n"
                                   "out=\"\"\n"
                                   "while [ \"$#\" -gt 0 ]; do\n"
                                   "  if [ \"$1\" = \"--output\" ]; then out=\"$2\"; shift 2; continue; fi\n"
                                   "  shift\n"
                                   "done\n"
                                   "echo \"dyn_stdout\"\n"
                                   "echo \"not json\" >\"$out\"\n"
                                   "exit 0\n");

    WorkerConfig config;
    config.mode = ExecutionMode::Dynamo;
    config.dynamo_launcher = "/bin/sh";
    config.dynamo_runner_binary = runner_bin.string();
    fragment::PartitionInfo part;
    part.id = "p1";
    BackendRequest request{part,
                           tmp.string(),
                           (tmp / "prog.asm").string(),
                           (tmp / "prog.bin").string(),
                           {{"rax", 0}},
                           {{"rax", 0}},
                           {},
                           {}};

    auto connector = make_backend_connector(config);
    fragment::ExecutionResult result = connector->execute(request);
    EXPECT_FALSE(result.success);
    EXPECT_FALSE(result.error_message.empty());
}

TEST(BackendConnector, DynamoBackendExitCodeSetsErrorMessage) {
    auto tmp = make_tmp_dir("backend_exit_code");
    auto runner_bin = write_script(tmp, "runner.sh",
                                   "#!/bin/sh\n"
                                   "out=\"\"\n"
                                   "while [ \"$#\" -gt 0 ]; do\n"
                                   "  if [ \"$1\" = \"--output\" ]; then out=\"$2\"; shift 2; continue; fi\n"
                                   "  shift\n"
                                   "done\n"
                                   "cat >\"$out\" <<'EOF'\n"
                                   "{\n"
                                   "  \"success\":true,\n"
                                   "  \"error\":\"\",\n"
                                   "  \"stdout\":\"\",\n"
                                   "  \"stderr\":\"\",\n"
                                   "  \"fd_outputs\":{},\n"
                                   "  \"initial_regs\":[],\n"
                                   "  \"final_regs\":[],\n"
                                   "  \"memory_patches\":[],\n"
                                   "  \"instructions\":1,\n"
                                   "  \"memory_accesses\":1\n"
                                   "}\n"
                                   "EOF\n"
                                   "exit 9\n");

    WorkerConfig config;
    config.mode = ExecutionMode::Dynamo;
    config.dynamo_launcher = "/bin/sh";
    config.dynamo_runner_binary = runner_bin.string();
    fragment::PartitionInfo part;
    part.id = "p1";
    BackendRequest request{part,
                           tmp.string(),
                           (tmp / "prog.asm").string(),
                           (tmp / "prog.bin").string(),
                           {{"rax", 0}},
                           {{"rax", 0}},
                           {},
                           {}};

    auto connector = make_backend_connector(config);
    fragment::ExecutionResult result = connector->execute(request);
    EXPECT_TRUE(result.success);
    EXPECT_NE(std::string::npos, result.error_message.find("DynamoRIO en erreur"));
}

}  // namespace worker
