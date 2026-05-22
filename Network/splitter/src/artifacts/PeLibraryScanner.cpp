#include "artifacts/PeLibraryScanner.hpp"

#include <cctype>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <utility>

#include "support/Env.hpp"
#include "support/ShellCommand.hpp"
#include "support/StringUtil.hpp"

namespace splitter {

namespace {

std::string wrap_command(const std::string& command) {
    std::string wrapper;
    if (auto env = GetEnv("SILICIUM_LIB_DETECT_WRAPPER"))
        wrapper = *env;
    if (wrapper.empty())
        return command;
    return wrapper + " " + command;
}

bool is_probable_symbol(const std::string& token) {
    if (token.empty())
        return false;
    if (token == "-" || token == "Table" || token == "Bound-To")
        return false;
    if (token.find(':') != std::string::npos)
        return false;
    if (token.rfind("0x", 0) == 0)
        return false;

    bool has_alpha = false;
    for (const char ch : token) {
        const bool ok = std::isalnum(static_cast<unsigned char>(ch))
                        || ch == '_'
                        || ch == '@'
                        || ch == '?'
                        || ch == '$'
                        || ch == '.';
        if (!ok)
            return false;
        if (std::isalpha(static_cast<unsigned char>(ch)))
            has_alpha = true;
    }
    return has_alpha;
}

}  // namespace

std::pair<std::vector<LibraryInfo>, std::unordered_map<std::string, std::string>>
PeLibraryScanner::parse_imports(const std::string& output) {
    std::vector<LibraryInfo> libraries;
    std::unordered_map<std::string, std::string> symbol_index;
    std::set<std::string> known_libs;
    std::string current_library;

    std::regex dll_regex(R"(DLL Name:\s*([^\s]+))");
    std::smatch match;

    std::istringstream stream(output);
    std::string line;
    while (std::getline(stream, line)) {
        const std::string trimmed = Trim(line);
        if (trimmed.empty())
            continue;

        if (std::regex_search(trimmed, match, dll_regex) && match.size() > 1) {
            current_library = match[1].str();
            if (known_libs.insert(current_library).second) {
                LibraryInfo info;
                info.SetName(current_library);
                info.SetPath("");
                info.SetSoname(current_library);
                libraries.push_back(std::move(info));
            }
            continue;
        }

        if (current_library.empty())
            continue;

        // Typical objdump import lines end with the imported symbol name.
        std::istringstream parser(trimmed);
        std::string token;
        std::string last;
        while (parser >> token)
            last = token;

        if (!is_probable_symbol(last))
            continue;
        if (symbol_index.find(last) == symbol_index.end())
            symbol_index.emplace(last, current_library);
    }

    return {libraries, symbol_index};
}

std::vector<LibraryInfo> PeLibraryScanner::DetectLibraries(const std::string& binary_path) const {
    last_symbol_index_.clear();
    const std::string command = wrap_command("objdump -p " + ShellQuote(binary_path) + " 2>/dev/null");
    try {
        const std::string output = ExecCommand(command);
        auto parsed = parse_imports(output);
        last_symbol_index_ = std::move(parsed.second);
        return parsed.first;
    } catch (const std::exception&) {
        return {};
    }
}

std::unordered_map<std::string, std::string> PeLibraryScanner::BuildSymbolIndex(
    const std::vector<LibraryInfo>&) const {
    return last_symbol_index_;
}

}  // namespace splitter
