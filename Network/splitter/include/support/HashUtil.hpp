#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <vector>

#include "support/FnvHasher.hpp"
#include "support/HashService.hpp"

namespace splitter {

std::string HashBytes(const std::vector<uint8_t>& data);
std::string HashFile(const std::string& path);
std::string HashString(const std::string& data);

void SetGlobalHashService(HashService service);
const HashService& GetGlobalHashService();

// Version orientée service (objet configurable).
class HashUtilService {
public:
    HashUtilService() = default;
    explicit HashUtilService(HashService service);

    std::string HashBytes(const std::vector<uint8_t>& data) const;
    std::string HashFile(const std::string& path) const;
    std::string HashString(const std::string& data) const;

private:
    HashService service_;
};

}  // namespace splitter
