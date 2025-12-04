#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <vector>

namespace splitter {

std::string HashBytes(const std::vector<uint8_t>& data);
std::string HashFile(const std::string& path);
std::string HashString(const std::string& data);

}  // namespace splitter
