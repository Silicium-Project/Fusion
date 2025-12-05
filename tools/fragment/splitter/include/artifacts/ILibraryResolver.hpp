#pragma once

#include <string>
#include <vector>

#include "core/LibraryInfo.hpp"

namespace splitter {

class ILibraryResolver {
public:
    virtual ~ILibraryResolver() = default;
    virtual std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const = 0;
};

}  // namespace splitter
