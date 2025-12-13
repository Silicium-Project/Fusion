#pragma once

#include "artifacts/ILibraryResolver.hpp"

namespace splitter {

// Variante readelf-only si ldd est indisponible ou non souhaité.
class ReadelfLibraryResolver : public ILibraryResolver {
public:
    std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const override;
};

}  // namespace splitter
