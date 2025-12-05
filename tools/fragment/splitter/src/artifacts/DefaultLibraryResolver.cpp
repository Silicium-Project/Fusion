#include "artifacts/DefaultLibraryResolver.hpp"

#include <cstdlib>
#include <regex>
#include <sstream>

#include "artifacts/ReadelfLibraryResolver.hpp"
#include "support/Env.hpp"
#include "support/ShellCommand.hpp"

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

std::vector<LibraryInfo> DetectLibrariesWithLdd(const std::string& binary_path) {
    std::vector<LibraryInfo> libraries;
    const std::string command = WrapCommand("ldd " + ShellQuote(binary_path) + " 2>/dev/null");

    try {
        const std::string output = ExecCommand(command);
        std::istringstream stream(output);
        std::string line;
        std::regex mapping_regex(R"(^\s*([^\s]+)\s+=>\s+([^\s]+))");
        std::regex direct_regex(R"(^\s*([^\s]+)\s+\((0x[0-9a-fA-F]+)\))");
        std::smatch match;

        while (std::getline(stream, line)) {
            if (std::regex_search(line, match, mapping_regex) && match.size() > 2) {
                const std::string name = match[1].str();
                const std::string path = match[2].str();
                if (path == "not" || path == "found")
                    continue;
                if (!path.empty() && path[0] == '/') {
                    LibraryInfo info;
                    info.SetName(name);
                    info.SetPath(path);
                    info.SetSoname(name);
                    libraries.push_back(std::move(info));
                }
            } else if (std::regex_search(line, match, direct_regex) && match.size() > 1) {
                continue;
            }
        }
    } catch (const std::exception&) {
        return {};
    }
    return libraries;
}

}  // namespace

std::vector<LibraryInfo> DefaultLibraryResolver::DetectLibraries(const std::string& binary_path) const {
    auto libraries = DetectLibrariesWithLdd(binary_path);
    if (!libraries.empty())
        return libraries;

    ReadelfLibraryResolver fallback;
    return fallback.DetectLibraries(binary_path);
}

}  // namespace splitter
