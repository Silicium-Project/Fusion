#pragma once

#include <memory>
#include <string>

#include "artifacts/ILibraryScanner.hpp"

namespace splitter {

class LibraryScannerFactory {
public:
    // resolver: "ldd" ou "readelf" (défaut auto si vide)
    // indexer: "nm" ou "objdump" (défaut auto si vide)
    static std::shared_ptr<ILibraryScanner> Create(const std::string& resolver,
                                                   const std::string& indexer);
};

}  // namespace splitter
