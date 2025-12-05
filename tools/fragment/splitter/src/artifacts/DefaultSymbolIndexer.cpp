#include "artifacts/DefaultSymbolIndexer.hpp"

#include <set>
#include <sstream>

#include "support/ShellCommand.hpp"
#include "support/StringUtil.hpp"

namespace splitter {

std::set<std::string> DefaultSymbolIndexer::ListExportedSymbols(const std::string& path) const {
    if (path.empty())
        return {};

    std::set<std::string> symbols;
    const std::string command = "nm -D --defined-only " + ShellQuote(path) + " 2>/dev/null";

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

std::unordered_map<std::string, std::string> DefaultSymbolIndexer::BuildSymbolIndex(
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
