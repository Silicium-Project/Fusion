#include "support/ShellCommand.hpp"

#include <array>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>

namespace splitter {

namespace {

using PipeHandle = std::unique_ptr<std::FILE, decltype(&pclose)>;

class PipeReader {
public:
    explicit PipeReader(const std::string& cmd) {
        PipeHandle opened(popen(cmd.c_str(), "r"), &pclose);
        if (!opened)
            throw std::runtime_error("popen() failed");
        handle_ = std::move(opened);
    }

    PipeReader(const PipeReader&) = delete;
    PipeReader& operator=(const PipeReader&) = delete;

    bool ReadLine(std::array<char, 128>& buffer, std::string& out) {
        if (!handle_)
            return false;
        if (fgets(buffer.data(), static_cast<int>(buffer.size()), handle_.get()) == nullptr)
            return false;
        out.append(buffer.data());
        return true;
    }

private:
    PipeHandle handle_{nullptr, &pclose};
};

}  // namespace

std::string ExecCommand(const std::string& cmd) {
    std::array<char, 128> buffer;
    std::string result;

    PipeReader pipe(cmd);
    while (pipe.ReadLine(buffer, result)) {
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
