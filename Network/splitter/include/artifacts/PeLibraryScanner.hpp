#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "artifacts/ILibraryScanner.hpp"

namespace splitter {

class PeLibraryScanner : public ILibraryScanner {
public:
    std::vector<LibraryInfo> DetectLibraries(const std::string& binary_path) const override;
    std::unordered_map<std::string, std::string> BuildSymbolIndex(
        const std::vector<LibraryInfo>& libraries) const override;

private:
    static std::pair<std::vector<LibraryInfo>, std::unordered_map<std::string, std::string>>
    parse_imports(const std::string& output);

    mutable std::unordered_map<std::string, std::string> last_symbol_index_;
};

}  // namespace splitter
