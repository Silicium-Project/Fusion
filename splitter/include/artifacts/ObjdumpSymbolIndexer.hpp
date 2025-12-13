#pragma once

#include "artifacts/ISymbolIndexer.hpp"

namespace splitter {

// Indexeur basé sur objdump -T (en cas d'absence de nm).
class ObjdumpSymbolIndexer : public ISymbolIndexer {
public:
    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const override;
};

}  // namespace splitter
