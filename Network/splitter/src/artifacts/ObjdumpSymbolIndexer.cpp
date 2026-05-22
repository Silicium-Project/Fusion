#include "artifacts/ObjdumpSymbolIndexer.hpp"

#include <set>
#include <sstream>

#include "support/ShellCommand.hpp"
#include "support/StringUtil.hpp"

namespace splitter {

std::unordered_map<std::string, std::string> ObjdumpSymbolIndexer::BuildSymbolIndex(
    const std::vector<LibraryInfo>& libraries) const {
    std::unordered_map<std::string, std::string> index;
    for (const auto& entry : libraries) {
        if (entry.Path().empty())
            continue;

        std::set<std::string> symbols;
        const std::string command = "objdump -T " + ShellQuote(entry.Path()) + " 2>/dev/null";
        try {
            const std::string output = ExecCommand(command);
            std::istringstream stream(output);
            std::string line;
            while (std::getline(stream, line)) {
                std::istringstream parser(Trim(line));
                std::string addr, type, bind, vis, ndx, name;
                if (!(parser >> addr >> type >> bind >> vis >> ndx >> name))
                    continue;
                if (!name.empty()) {
                    auto at = name.find('@');
                    if (at != std::string::npos)
                        name = name.substr(0, at);
                    symbols.insert(name);
                }
            }
        } catch (const std::exception&) {
            continue;
        }

        for (const auto& sym : symbols)
            index.emplace(sym, entry.Name());
    }
    return index;
}

}  // namespace splitter
