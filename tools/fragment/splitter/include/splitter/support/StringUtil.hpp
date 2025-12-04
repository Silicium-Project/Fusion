#pragma once

#include <set>
#include <string>
#include <sstream>
#include <vector>

#include "splitter/support/FlatMap.hpp"

namespace splitter {

std::string JsonEscape(const std::string& input);
std::string Trim(const std::string& str);
std::vector<std::string> SplitString(const std::string& str, char delimiter);

std::string VectorToJson(const std::vector<std::string>& values);

// Conversion générique vers JSON pour toute collection itérable de strings.
template <typename Container>
std::string RangeToJson(const Container& values) {
    std::vector<std::string> vectorized(values.begin(), values.end());
    return VectorToJson(vectorized);
}

inline std::string SetToJson(const std::set<std::string>& values) {
    return RangeToJson(values);
}

template <typename Map>
std::string MapToJson(const Map& values) {
    std::vector<std::string> entries;
    entries.reserve(values.size());
    for (const auto& kv : values)
        entries.push_back('"' + JsonEscape(kv.first) + "\": \"" + JsonEscape(kv.second) + '"');
    std::ostringstream oss;
    oss << "{";
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i)
            oss << ", ";
        oss << entries[i];
    }
    oss << "}";
    return oss.str();
}

}  // namespace splitter
