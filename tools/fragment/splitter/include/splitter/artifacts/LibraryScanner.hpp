#pragma once

#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include "splitter/artifacts/ILibraryScanner.hpp"
#include "splitter/core/LibraryInfo.hpp"

namespace splitter {

class LibraryScanner : public ILibraryScanner {
public:
    ~LibraryScanner() override;
    std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const override;
    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const override;

private:
    std::set<std::string> ListExportedSymbols(const std::string& path) const;
};

}  // namespace splitter
