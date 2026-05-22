#include "artifacts/LibraryScanner.hpp"

#include <utility>

#include "artifacts/DefaultLibraryResolver.hpp"
#include "artifacts/DefaultSymbolIndexer.hpp"

namespace splitter {

LibraryScanner::LibraryScanner(std::unique_ptr<ILibraryResolver> resolver,
                               std::unique_ptr<ISymbolIndexer> indexer)
    : resolver_(resolver ? std::move(resolver) : std::make_unique<DefaultLibraryResolver>()),
      indexer_(indexer ? std::move(indexer) : std::make_unique<DefaultSymbolIndexer>()) {}

LibraryScanner::~LibraryScanner() = default;

std::vector<LibraryInfo> LibraryScanner::DetectLibraries(const std::string& binary_path) const {
    return resolver_->DetectLibraries(binary_path);
}

std::unordered_map<std::string, std::string> LibraryScanner::BuildSymbolIndex(
    const std::vector<LibraryInfo>& libraries) const {
    return indexer_->BuildSymbolIndex(libraries);
}

}  // namespace splitter
