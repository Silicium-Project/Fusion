#include "artifacts/ReadelfLibraryResolver.hpp"

#include <cstdlib>
#include <regex>
#include <set>
#include <sstream>

#include "support/ShellCommand.hpp"
#include "support/Env.hpp"

namespace splitter {

namespace {

std::string WrapCommand(const std::string& command) {
    std::string wrapper;
    if (auto env = GetEnv("SILICIUM_LIB_DETECT_WRAPPER"))
        wrapper = *env;
    if (wrapper.empty())
        return command;
    return wrapper + " " + command;
}

std::vector<std::string> DetectNeededViaReadelf(const std::string& binary_path) {
    std::set<std::string> unique;
    const std::string command = WrapCommand("readelf -d " + ShellQuote(binary_path) + " 2>/dev/null");

    try {
        const std::string output = ExecCommand(command);
        std::regex needed_regex(R"(\(NEEDED\).*\[(.+?)\])");
        std::smatch match;
        std::istringstream stream(output);
        std::string line;
        while (std::getline(stream, line))
            if (std::regex_search(line, match, needed_regex) && match.size() > 1)
                unique.insert(match[1].str());
    } catch (const std::exception&) {
        return {};
    }
    return std::vector<std::string>(unique.begin(), unique.end());
}

}  // namespace

std::vector<LibraryInfo> ReadelfLibraryResolver::DetectLibraries(const std::string& binary_path) const {
    std::vector<LibraryInfo> libraries;
    auto names = DetectNeededViaReadelf(binary_path);
    for (const auto& name : names) {
        LibraryInfo info;
        info.SetName(name);
        info.SetPath("");
        info.SetSoname(name);
        libraries.push_back(std::move(info));
    }
    return libraries;
}

}  // namespace splitter
