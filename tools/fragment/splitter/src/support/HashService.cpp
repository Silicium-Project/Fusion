#include "splitter/support/HashService.hpp"

#include <fstream>

namespace splitter {

std::string HashService::HashBytes(const std::vector<uint8_t>& data) const {
    auto hasher = MakeHasher();
    hasher->Reset();
    for (uint8_t byte : data)
        hasher->AddByte(byte);
    return hasher->Hex();
}

std::string HashService::HashString(std::string_view data) const {
    auto hasher = MakeHasher();
    hasher->Reset();
    if (!data.empty())
        hasher->AddString(data);
    return hasher->Hex();
}

std::string HashService::HashFile(const std::string& path) const {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open())
        return {};
    std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());
    return HashBytes(buffer);
}

}  // namespace splitter
