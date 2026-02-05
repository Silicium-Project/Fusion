#include <gtest/gtest.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

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

bool wait_for_file(const std::filesystem::path& path, int retries = 50, int delay_ms = 20) {
    for (int i = 0; i < retries; ++i) {
        if (std::filesystem::exists(path))
            return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
    }
    return false;
}

std::string resolve_python() {
    if (const char* env = std::getenv("PYTHON"); env && *env)
        return env;
#if defined(_WIN32)
    return "python";
#else
    return "python3";
#endif
}

struct HttpStubServer {
    std::filesystem::path dir;
    std::filesystem::path script;
    std::filesystem::path port_file;
    std::filesystem::path payload_file;
    std::filesystem::path response_file;
    FILE* process = nullptr;
    int port = 0;

    explicit HttpStubServer(std::filesystem::path base) : dir(std::move(base)) {
        port_file = dir / "port.txt";
        payload_file = dir / "payload.json";
        response_file = dir / "response.json";
    }

    void start() {
        std::ofstream(response_file) << "{\n"
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
        script = write_script(dir, "stub_http.py",
                              "import http.server\n"
                              "import socketserver\n"
                              "import threading\n"
                              "import sys\n"
                              "\n"
                              "port_file = sys.argv[1]\n"
                              "payload_file = sys.argv[2]\n"
                              "response_file = sys.argv[3]\n"
                              "\n"
                              "class Handler(http.server.BaseHTTPRequestHandler):\n"
                              "    def do_POST(self):\n"
                              "        length = int(self.headers.get('Content-Length', '0'))\n"
                              "        body = self.rfile.read(length)\n"
                              "        with open(payload_file, 'wb') as f:\n"
                              "            f.write(body)\n"
                              "        with open(response_file, 'rb') as f:\n"
                              "            payload = f.read()\n"
                              "        self.send_response(200)\n"
                              "        self.send_header('Content-Type', 'application/json')\n"
                              "        self.end_headers()\n"
                              "        self.wfile.write(payload)\n"
                              "        threading.Thread(target=httpd.shutdown, daemon=True).start()\n"
                              "    def log_message(self, *args):\n"
                              "        return\n"
                              "\n"
                              "with socketserver.TCPServer(('127.0.0.1', 0), Handler) as httpd:\n"
                              "    port = httpd.server_address[1]\n"
                              "    with open(port_file, 'w') as f:\n"
                              "        f.write(str(port))\n"
                              "    httpd.serve_forever()\n");
        std::ostringstream cmd;
        cmd << resolve_python() << " \"" << script.string() << "\""
            << " \"" << port_file.string() << "\""
            << " \"" << payload_file.string() << "\""
            << " \"" << response_file.string() << "\"";
        process = popen(cmd.str().c_str(), "r");
        if (!process)
            throw std::runtime_error("Failed to start HTTP stub server");
        if (!wait_for_file(port_file))
            throw std::runtime_error("HTTP stub server did not start");
        port = std::stoi(read_file(port_file));
    }

    void stop() {
        if (process) {
            pclose(process);
            process = nullptr;
        }
    }

    ~HttpStubServer() { stop(); }
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
    HttpStubServer server(tmp);
    server.start();

    WorkerConfig config;
    config.connector = ConnectorMode::Http;
    config.connector_endpoint = "http://127.0.0.1:" + std::to_string(server.port) + "/execute";
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

    const std::string payload = read_file(server.payload_file);
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
