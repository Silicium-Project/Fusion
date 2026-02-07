#include "support/ShellCommand.hpp"

#include <array>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <sstream>

namespace splitter {

std::string ExecCommand(const std::string& cmd) {
    std::string full_cmd = cmd;
    if (full_cmd.find("2>") == std::string::npos)
        full_cmd += " 2>&1";

    std::array<char, 128> buffer;
    std::string result;

    std::FILE* pipe = popen(full_cmd.c_str(), "r");
    if (!pipe)
        throw std::runtime_error("popen() failed");

    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr)
        result.append(buffer.data());

    const int status = pclose(pipe);
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
