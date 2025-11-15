#pragma once

#include "fragment/common.hpp"

namespace fragment {

std::string ascii_from_uint64(uint64_t value);

std::string trim(const std::string& str);

size_t find_matching(const std::string& text, size_t start, char open_char, char close_char);

std::string extract_json_string(const std::string& object_text, const std::string& key);

std::vector<std::string> parse_json_string_array(const std::string& array_text);

std::vector<std::string> extract_json_array(const std::string& object_text, const std::string& key);

bool extract_json_bool(const std::string& object_text, const std::string& key, bool default_value = false);

uint64_t extract_json_uint64(const std::string& object_text,
                             const std::string& key,
                             uint64_t default_value = 0);

}  // namespace fragment
