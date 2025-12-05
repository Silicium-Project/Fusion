#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "core/LibraryInfo.hpp"

namespace splitter {

class ISymbolIndexer {
public:
    virtual ~ISymbolIndexer() = default;
    virtual std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const = 0;
};

}  // namespace splitter
