#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <vector>

#include "support/FnvHasher.hpp"
#include "support/HashService.hpp"

namespace splitter {

// Fonctions utilitaires génériques pour hacher des données avec n'importe quel
// hasher respectant l'interface AddByte/AddString/Hex (IHashAlgorithm, FnvHasher, etc.)
template <typename Hasher>
std::string HashBytesWith(const std::vector<uint8_t>& data, Hasher hasher) {
    for (uint8_t byte : data)
        hasher.AddByte(byte);
    return hasher.Hex();
}

template <typename Hasher>
std::string HashStringWith(std::string_view data, Hasher hasher) {
    if (!data.empty())
        hasher.AddString(data);
    return hasher.Hex();
}

std::string HashBytes(const std::vector<uint8_t>& data);
std::string HashFile(const std::string& path);
std::string HashString(const std::string& data);

void SetGlobalHashService(HashService service);
const HashService& GetGlobalHashService();

// Version orientée service (objet configurable).
class HashUtilService {
public:
    HashUtilService() = default;
    explicit HashUtilService(HashService service) : service_(std::move(service)) {}

    std::string HashBytes(const std::vector<uint8_t>& data) const { return service_.HashBytes(data); }
    std::string HashFile(const std::string& path) const { return service_.HashFile(path); }
    std::string HashString(const std::string& data) const { return service_.HashString(data); }

private:
    HashService service_;
};

}  // namespace splitter
