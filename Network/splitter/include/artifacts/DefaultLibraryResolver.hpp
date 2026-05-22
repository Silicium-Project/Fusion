#pragma once

#include "artifacts/ILibraryResolver.hpp"

namespace splitter {

class DefaultLibraryResolver : public ILibraryResolver {
public:
    std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const override;
};

}  // namespace splitter
