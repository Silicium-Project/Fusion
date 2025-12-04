#pragma once

#include <set>
#include <string>
#include <vector>

namespace splitter {

std::string JsonEscape(const std::string& input);
std::string Trim(const std::string& str);
std::vector<std::string> SplitString(const std::string& str, char delimiter);

std::string VectorToJson(const std::vector<std::string>& values);
std::string SetToJson(const std::set<std::string>& values);

}  // namespace splitter
