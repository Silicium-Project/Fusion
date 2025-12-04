#include "splitter/support/HashUtil.hpp"

#include <fstream>
#include <functional>
#include <iomanip>
#include <sstream>
#include <string_view>

namespace splitter {

std::string HashBytes(const std::vector<uint8_t>& data) {
    std::hash<std::string_view> hasher;
    std::string_view view(reinterpret_cast<const char*>(data.data()), data.size());
    auto value = hasher(view);
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << value;
    return oss.str();
}

std::string HashFile(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open())
        return {};
    std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());
    return HashBytes(buffer);
}

std::string HashString(const std::string& data) {
    std::hash<std::string_view> hasher;
    auto value = hasher(std::string_view(data));
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << value;
    return oss.str();
}

}  // namespace splitter
