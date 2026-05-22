#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace splitter {

// Lit une variable d'environnement et retourne une copie (vide si absente).
std::optional<std::string> GetEnv(std::string_view key);

}  // namespace splitter
