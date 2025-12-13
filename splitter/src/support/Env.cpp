#include "support/Env.hpp"

#include <cstdlib>

namespace splitter {

std::optional<std::string> GetEnv(std::string_view key) {
    std::string key_str(key);
    const char* value = std::getenv(key_str.c_str());
    if (!value)
        return std::nullopt;
    return std::string(value);
}

}  // namespace splitter
