#include "support/StringUtil.hpp"

#include <algorithm>
#include <set>
#include <sstream>

#include "support/FlatMap.hpp"
#include "support/FlatSet.hpp"
namespace splitter {

std::string JsonEscape(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (char c : input) {
        switch (c) {
            case '\\': result += "\\\\"; break;
            case '"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default: result += c; break;
        }
    }
    return result;
}

std::string Trim(const std::string& str) {
    std::size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
        return "";
    std::size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, last - first + 1);
}

std::vector<std::string> SplitString(const std::string& str, char delimiter) {
    std::vector<std::string> tokens;
    std::stringstream ss(str);
    std::string token;
    while (std::getline(ss, token, delimiter))
        tokens.push_back(token);
    return tokens;
}

std::string VectorToJson(const std::vector<std::string>& values) {
    std::ostringstream oss;
    oss << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i)
            oss << ", ";
        oss << '"' << JsonEscape(values[i]) << '"';
    }
    oss << "]";
    return oss.str();
}

std::string RangeToJson(const std::vector<std::string>& values) {
    return VectorToJson(values);
}

std::string RangeToJson(const FlatStringSet& values) {
    std::vector<std::string> vectorized(values.begin(), values.end());
    return VectorToJson(vectorized);
}

std::string SetToJson(const std::set<std::string>& values) {
    std::vector<std::string> vectorized(values.begin(), values.end());
    return VectorToJson(vectorized);
}

std::string MapToJson(const FlatMap<std::string, std::string>& values) {
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
