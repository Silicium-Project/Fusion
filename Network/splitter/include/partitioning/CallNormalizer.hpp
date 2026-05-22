#pragma once

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "support/StringUtil.hpp"

namespace splitter {

using CallRef = std::pair<std::optional<uint64_t>, std::string>;

// Politique par défaut : normalisation des symboles externes et détection GUI.
class DefaultCallNormalizer {
public:
    std::string Normalize(const CallRef& call) const;
    bool IsGuiSymbol(const std::string& symbol) const;

private:
    std::vector<std::string> GuiPrefixes() const;
};

}  // namespace splitter
