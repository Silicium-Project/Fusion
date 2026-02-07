#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>
#include <unistd.h>
#include <sys/wait.h>

#include <gtest/gtest.h>

#include "pipeline/PipelineFactory.hpp"
#include "pipeline/PipelineRunner.hpp"

namespace splitter {

namespace fs = std::filesystem;

namespace {

struct CmdResult {
    int code = 0;
    std::string stdout_data;
    std::string stderr_data;
};

std::string join_args(const std::vector<std::string>& args) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& arg : args) {
        if (!first)
            oss << ' ';
        first = false;
        oss << arg;
    }
    return oss.str();
}

CmdResult run_process(const std::vector<std::string>& args, const fs::path& cwd = {}) {
    if (args.empty())
        throw std::runtime_error("run_process: empty args");

    int out_pipe[2]{-1, -1};
    int err_pipe[2]{-1, -1};
    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0)
        throw std::runtime_error("run_process: pipe failed");

    pid_t pid = fork();
    if (pid < 0)
        throw std::runtime_error("run_process: fork failed");

    if (pid == 0) {
        if (!cwd.empty())
            chdir(cwd.c_str());
        dup2(out_pipe[1], STDOUT_FILENO);
        dup2(err_pipe[1], STDERR_FILENO);
        close(out_pipe[0]);
        close(out_pipe[1]);
        close(err_pipe[0]);
        close(err_pipe[1]);

        std::vector<char*> argv;
        argv.reserve(args.size() + 1);
        for (const auto& arg : args)
            argv.push_back(const_cast<char*>(arg.c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        _exit(127);
    }

    close(out_pipe[1]);
    close(err_pipe[1]);

    auto reader = [](int fd, std::string& out) {
        char buffer[4096];
        ssize_t n = 0;
        while ((n = read(fd, buffer, sizeof(buffer))) > 0)
            out.append(buffer, static_cast<size_t>(n));
    };

    CmdResult result;
    std::thread out_thread(reader, out_pipe[0], std::ref(result.stdout_data));
    std::thread err_thread(reader, err_pipe[0], std::ref(result.stderr_data));

    int status = 0;
    waitpid(pid, &status, 0);

    out_thread.join();
    err_thread.join();
    close(out_pipe[0]);
    close(err_pipe[0]);

    if (WIFEXITED(status))
        result.code = WEXITSTATUS(status);
    else if (WIFSIGNALED(status))
        result.code = 128 + WTERMSIG(status);
    else
        result.code = status;

    return result;
}

}  // namespace

TEST(PipelineRealIntegration, RunsEndToEndOnCompiledBinary) {
    fs::path tmp_dir = fs::temp_directory_path() / "splitter_real_integration";
    fs::create_directories(tmp_dir);
    fs::path src_path = tmp_dir / "sample.c";
    fs::path bin_path = tmp_dir / "sample_bin";
    fs::path out_dir = tmp_dir / "out";

    {
        std::ofstream src(src_path);
        src << "#include <stdio.h>\n"
               "int main(){\n"
               "  int acc = 0;\n"
               "  for(int i=0;i<4;++i) acc += i;\n"
               "  printf(\"acc=%d\\n\", acc);\n"
               "  return acc;\n"
               "}\n";
    }

    auto compile = run_process({"gcc", "-O0", "-g", "-no-pie", src_path.string(), "-o", bin_path.string()});
    ASSERT_EQ(0, compile.code)
        << "Compilation du binaire de test échouée: "
        << join_args({"gcc", "-O0", "-g", "-no-pie", src_path.string(), "-o", bin_path.string()})
        << "\nstdout:\n" << compile.stdout_data
        << "\nstderr:\n" << compile.stderr_data;

    PipelineConfig config;
    config.binary_path = BinaryPath(bin_path.string());
    config.output_dir = OutputDir(out_dir.string());
    config.dump_full_disassembly = false;

    auto runner = PipelineFactory::BuildDefault(std::move(config));
    EXPECT_EQ(0, runner->Run());

    fs::path summary = out_dir / "summary.json";
    EXPECT_TRUE(fs::exists(summary));
    if (fs::exists(summary)) {
        EXPECT_GT(fs::file_size(summary), 0u);
    }

    std::error_code ec;
    fs::remove_all(tmp_dir, ec);
}

}  // namespace splitter
