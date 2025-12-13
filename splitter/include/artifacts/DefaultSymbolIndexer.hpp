#pragma once

#include <set>

#include "artifacts/ISymbolIndexer.hpp"

namespace splitter {

class DefaultSymbolIndexer : public ISymbolIndexer {
public:
    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const override;

private:
    std::set<std::string> ListExportedSymbols(const std::string& path) const;
};

}  // namespace splitter
