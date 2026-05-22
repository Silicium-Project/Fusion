#include "support/ShellCommand.hpp"

#include <array>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <sstream>

namespace splitter {

namespace {

int close_pipe(std::FILE* pipe) {
    return pclose(pipe);
}

using PipeHandle = std::unique_ptr<std::FILE, decltype(&close_pipe)>;

int close_pipe_and_get_status(PipeHandle& pipe) {
    if (!pipe)
        return -1;
    auto raw = pipe.release();
    return close_pipe(raw);
}

}  // namespace

std::string ExecCommand(const std::string& cmd) {
    std::string full_cmd = cmd;
    if (full_cmd.find("2>") == std::string::npos)
        full_cmd += " 2>&1";

    std::array<char, 128> buffer;
    std::string result;

    PipeHandle pipe(popen(full_cmd.c_str(), "r"), &close_pipe);
    if (!pipe)
        throw std::runtime_error("popen() failed");

    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr)
        result.append(buffer.data());

    const int status = close_pipe_and_get_status(pipe);
    if (status != 0) {
        std::ostringstream oss;
        oss << "Command failed (" << status << "): " << cmd;
        if (!result.empty())
            oss << "\n" << result;
        throw std::runtime_error(oss.str());
    }

    return result;
}

std::string ShellQuote(const std::string& path) {
    std::string quoted = "'";
    for (char ch : path) {
        if (ch == '\'')
            quoted += "'\\''";
        else
            quoted.push_back(ch);
    }
    quoted += "'";
    return quoted;
}

}  // namespace splitter
