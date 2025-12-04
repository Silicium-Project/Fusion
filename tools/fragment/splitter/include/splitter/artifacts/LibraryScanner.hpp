#pragma once

#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include <memory>

#include "splitter/artifacts/ILibraryScanner.hpp"
#include "splitter/artifacts/ILibraryResolver.hpp"
#include "splitter/artifacts/ISymbolIndexer.hpp"
#include "splitter/core/LibraryInfo.hpp"

namespace splitter {

class LibraryScanner : public ILibraryScanner {
public:
    LibraryScanner(std::unique_ptr<ILibraryResolver> resolver = nullptr,
                   std::unique_ptr<ISymbolIndexer> indexer = nullptr);
    ~LibraryScanner() override;

    std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const override;
    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const override;

private:
    std::unique_ptr<ILibraryResolver> resolver_;
    std::unique_ptr<ISymbolIndexer> indexer_;
};

}  // namespace splitter
