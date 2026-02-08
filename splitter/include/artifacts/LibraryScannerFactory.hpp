#pragma once

#include <memory>
#include <string>

#include "artifacts/ILibraryScanner.hpp"

namespace splitter {

class LibraryScannerFactory {
public:
    // resolver: "ldd", "readelf" or "pe" (auto when empty)
    // indexer: "nm", "objdump" or "pe" (auto when empty)
    static std::shared_ptr<ILibraryScanner> Create(const std::string& resolver,
                                                   const std::string& indexer);
};

}  // namespace splitter
