#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "partition/PartitionSummary.hpp"
#include "worker/backend/BackendConnector.hpp"
#include "worker/runtime/DynamoRunner.hpp"

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

std::string read_file(const std::filesystem::path& path) {
    std::ifstream file(path);
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

class ScopedEnvVar {
public:
    ScopedEnvVar(const char* name, const std::string& value) : name_(name) {
        if (const char* old = std::getenv(name_); old != nullptr) {
            had_old_ = true;
            old_value_ = old;
        }
        set(value);
    }

    ~ScopedEnvVar() {
        if (had_old_)
            set(old_value_);
        else
            unset();
    }

    ScopedEnvVar(const ScopedEnvVar&) = delete;
    ScopedEnvVar& operator=(const ScopedEnvVar&) = delete;

private:
    void set(const std::string& value) const {
#if defined(_WIN32)
        _putenv_s(name_, value.c_str());
#else
        setenv(name_, value.c_str(), 1);
#endif
    }

    void unset() const {
#if defined(_WIN32)
        _putenv_s(name_, "");
#else
        unsetenv(name_);
#endif
    }

    const char* name_ = nullptr;
    bool had_old_ = false;
    std::string old_value_;
};

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

    auto tmp = make_tmp_dir("backend_http");
    auto response_path = tmp / "response.json";
    std::ofstream(response_path) << "{\n"
                                 << "  \"success\":true,\n"
                                 << "  \"error\":\"\",\n"
                                 << "  \"stdout\":\"ok\",\n"
                                 << "  \"stderr\":\"\",\n"
                                 << "  \"fd_outputs\":{},\n"
                                 << "  \"initial_regs\":[],\n"
                                 << "  \"final_regs\":[],\n"
                                 << "  \"memory_patches\":[],\n"
                                 << "  \"instructions\":1,\n"
                                 << "  \"memory_accesses\":0\n"
                                 << "}\n";
    config.connector_endpoint = "file://" + response_path.string();
    connector = make_backend_connector(config);
    res = connector->execute(req);
    EXPECT_TRUE(res.success);
    EXPECT_EQ("ok", res.program_stdout);
    EXPECT_EQ(1u, res.instructions_executed);
}

TEST(BackendConnector, HttpConnectorPostsPayloadToServer) {
    auto tmp = make_tmp_dir("backend_http_integration");
    auto response_path = tmp / "response.json";
    std::ofstream(response_path) << "{\n"
                                 << "  \"success\":true,\n"
                                 << "  \"error\":\"\",\n"
                                 << "  \"stdout\":\"http_ok\",\n"
                                 << "  \"stderr\":\"\",\n"
                                 << "  \"fd_outputs\":{},\n"
                                 << "  \"initial_regs\":[],\n"
                                 << "  \"final_regs\":[],\n"
                                 << "  \"memory_patches\":[],\n"
                                 << "  \"instructions\":2,\n"
                                 << "  \"memory_accesses\":1\n"
                                 << "}\n";

    const std::filesystem::path payload_capture_path = tmp / "captured_payload.json";
    const std::filesystem::path url_capture_path = tmp / "captured_url.txt";
    write_script(
        tmp,
        "curl",
        "#!/bin/sh\n"
        "set -eu\n"
        "payload_out=\"${SILICIUM_TEST_PAYLOAD_OUT:-}\"\n"
        "url_out=\"${SILICIUM_TEST_URL_OUT:-}\"\n"
        "response_file=\"${SILICIUM_TEST_RESPONSE_FILE:-}\"\n"
        "data_arg=\"\"\n"
        "url=\"\"\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--data-binary\" ]; then\n"
        "    data_arg=\"$2\"; shift 2; continue\n"
        "  fi\n"
        "  case \"$1\" in\n"
        "    http://*|https://*) url=\"$1\" ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        "if [ -n \"$url_out\" ]; then\n"
        "  printf '%s' \"$url\" >\"$url_out\"\n"
        "fi\n"
        "if [ -n \"$payload_out\" ] && [ -n \"$data_arg\" ]; then\n"
        "  case \"$data_arg\" in\n"
        "    @*) src=\"${data_arg#@}\" ;;\n"
        "    *) src=\"$data_arg\" ;;\n"
        "  esac\n"
        "  cat \"$src\" >\"$payload_out\"\n"
        "fi\n"
        "if [ -n \"$response_file\" ]; then\n"
        "  cat \"$response_file\"\n"
        "fi\n"
        "printf '\\n__SILICIUM_HTTP_STATUS__:200\\n'\n"
        "exit 0\n");

    const char* old_path = std::getenv("PATH");
    std::string new_path;
    if (old_path && *old_path)
        new_path = tmp.string() + ":" + old_path;
    else
        new_path = tmp.string();
    ScopedEnvVar scoped_path("PATH", new_path);
    ScopedEnvVar scoped_payload_out("SILICIUM_TEST_PAYLOAD_OUT", payload_capture_path.string());
    ScopedEnvVar scoped_url_out("SILICIUM_TEST_URL_OUT", url_capture_path.string());
    ScopedEnvVar scoped_response_file("SILICIUM_TEST_RESPONSE_FILE", response_path.string());

    WorkerConfig config;
    config.connector = ConnectorMode::Http;
    config.connector_endpoint = "http://127.0.0.1:12345/execute";
    fragment::PartitionInfo part;
    part.id = "p1";
    BackendRequest req{part,
                       tmp.string(),
                       (tmp / "prog.asm").string(),
                       (tmp / "prog.bin").string(),
                       {{"rax", 0x10}},
                       {{"rbx", 0x20}},
                       {},
                       {}};

    auto connector = make_backend_connector(config);
    fragment::ExecutionResult res = connector->execute(req);
    EXPECT_TRUE(res.success);
    EXPECT_EQ("http_ok", res.program_stdout);
    EXPECT_EQ(2u, res.instructions_executed);

    const std::string payload = read_file(payload_capture_path);
    EXPECT_EQ(config.connector_endpoint, read_file(url_capture_path));
    EXPECT_NE(std::string::npos, payload.find("\"type\":\"binary\""));
    EXPECT_NE(std::string::npos, payload.find("\"partition_id\":\"p1\""));
    EXPECT_NE(std::string::npos, payload.find("\"asm_path\""));
    EXPECT_NE(std::string::npos, payload.find("\"binary_path\""));
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
