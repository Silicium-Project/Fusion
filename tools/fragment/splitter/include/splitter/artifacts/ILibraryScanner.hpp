#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "splitter/artifacts/ILibraryResolver.hpp"
#include "splitter/artifacts/ISymbolIndexer.hpp"
#include "splitter/core/LibraryInfo.hpp"

namespace splitter {

class ILibraryScanner : public ILibraryResolver, public ISymbolIndexer {
public:
    virtual ~ILibraryScanner() = default;
    virtual std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const = 0;
    virtual std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const = 0;
};

}  // namespace splitter
