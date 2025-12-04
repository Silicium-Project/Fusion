#pragma once

#include <string>

namespace splitter {

std::string ExecCommand(const std::string& cmd);
std::string ShellQuote(const std::string& path);

}  // namespace splitter
