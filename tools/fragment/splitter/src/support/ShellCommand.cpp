#include "splitter/support/ShellCommand.hpp"

#include <array>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>

namespace splitter {

std::string ExecCommand(const std::string& cmd) {
    std::array<char, 128> buffer;
    std::string result;
    auto closer = [](FILE* fp) {
        if (fp)
            pclose(fp);
    };
    std::unique_ptr<FILE, decltype(closer)> pipe(popen(cmd.c_str(), "r"), closer);
    if (!pipe)
        throw std::runtime_error("popen() failed");

    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr)
        result += buffer.data();
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
