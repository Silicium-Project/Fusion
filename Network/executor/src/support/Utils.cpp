#include "support/Utils.hpp"

#include <algorithm>

namespace fragment {

std::string ascii_from_uint64(uint64_t value) {
    std::string s;
    for (int i = 0; i < 8; ++i) {
        char c = static_cast<char>((value >> (i * 8)) & 0xFF);
        if (c >= 32 && c <= 126)
            s.push_back(c);
        else
            s.push_back('.');
    }
    return s;
}

std::string trim(const std::string& str) {
    auto begin = std::find_if_not(str.begin(), str.end(), [](unsigned char c) {
        return c == ' ' || c == '\t' || c == '\r' || c == '\n';
    });
    auto end = std::find_if_not(str.rbegin(), str.rend(), [](unsigned char c) {
        return c == ' ' || c == '\t' || c == '\r' || c == '\n';
    }).base();
    if (begin >= end)
        return {};
    return std::string(begin, end);
}

}  // namespace fragment
