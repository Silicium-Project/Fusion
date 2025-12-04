#include "splitter/artifacts/LibraryScanner.hpp"

#include <optional>
#include <regex>
#include <sstream>
#include <unordered_map>

#include "splitter/support/ShellCommand.hpp"
#include "splitter/support/StringUtil.hpp"

namespace splitter {

LibraryScanner::~LibraryScanner() = default;

namespace {

std::string EnvWrapper() {
    const char* wrapper = std::getenv("SILICIUM_LIB_DETECT_WRAPPER");
    return (wrapper && *wrapper) ? std::string(wrapper) : std::string();
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

std::string WrapCommand(const std::string& command) {
    std::string wrapper = EnvWrapper();
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

std::vector<LibraryInfo> LibraryScanner::DetectLibraries(const std::string& binary_path) const {
    auto libraries = DetectLibrariesWithLdd(binary_path);
    if (!libraries.empty())
        return libraries;

    auto names = DetectNeededViaReadelf(binary_path);
    libraries.reserve(names.size());
    for (const auto& name : names) {
        LibraryInfo info;
        info.SetName(name);
        info.SetPath("");
        info.SetSoname(name);
        libraries.push_back(std::move(info));
    }
    return libraries;
}

std::set<std::string> LibraryScanner::ListExportedSymbols(const std::string& path) const {
    if (path.empty())
        return {};

    std::set<std::string> symbols;
    const std::string command = WrapCommand("nm -D --defined-only " + ShellQuote(path) + " 2>/dev/null");

    try {
        const std::string output = ExecCommand(command);
        std::istringstream stream(output);
        std::string line;

        while (std::getline(stream, line)) {
            std::istringstream parser(Trim(line));
            std::string address, type, name;
            if (!(parser >> address >> type >> name))
                continue;
            if (!name.empty()) {
                auto at = name.find('@');
                if (at != std::string::npos)
                    name = name.substr(0, at);
                symbols.insert(name);
            }
        }
    } catch (const std::exception&) {
        return {};
    }
    return symbols;
}

std::unordered_map<std::string, std::string> LibraryScanner::BuildSymbolIndex(
    const std::vector<LibraryInfo>& libraries) const {
    std::unordered_map<std::string, std::string> index;
    for (const auto& entry : libraries) {
        if (entry.Path().empty())
            continue;
        auto symbols = ListExportedSymbols(entry.Path());
        for (const auto& symbol : symbols)
            index.emplace(symbol, entry.Name());
    }
    return index;
}

}  // namespace splitter
