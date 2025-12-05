#include "splitter/artifacts/LibraryScannerFactory.hpp"

#include "splitter/artifacts/DefaultLibraryResolver.hpp"
#include "splitter/artifacts/DefaultSymbolIndexer.hpp"
#include "splitter/artifacts/LibraryScanner.hpp"
#include "splitter/artifacts/ObjdumpSymbolIndexer.hpp"
#include "splitter/artifacts/ReadelfLibraryResolver.hpp"

namespace splitter {

std::shared_ptr<ILibraryScanner> LibraryScannerFactory::Create(const std::string& resolver,
                                                               const std::string& indexer) {
    std::unique_ptr<ILibraryResolver> resolver_impl;
    if (resolver == "readelf")
        resolver_impl = std::make_unique<ReadelfLibraryResolver>();
    else
        resolver_impl = std::make_unique<DefaultLibraryResolver>();

    std::unique_ptr<ISymbolIndexer> indexer_impl;
    if (indexer == "objdump")
        indexer_impl = std::make_unique<ObjdumpSymbolIndexer>();
    else
        indexer_impl = std::make_unique<DefaultSymbolIndexer>();

    return std::make_shared<LibraryScanner>(std::move(resolver_impl), std::move(indexer_impl));
}

}  // namespace splitter
