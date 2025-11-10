#include "fragment/utils.hpp"

#include <cctype>
#include <sstream>

namespace fragment {

std::string ascii_from_uint64(uint64_t value) {
    std::string bytes;
    bytes.reserve(8);
    bool has_printable = false;
    for (int i = 0; i < 8; ++i) {
        unsigned char byte = static_cast<unsigned char>((value >> (i * 8)) & 0xFF);
        if (std::isprint(byte)) {
            bytes.push_back(static_cast<char>(byte));
            has_printable = true;
        } else if (byte != 0) {
            bytes.push_back('.');
        } else {
            bytes.push_back(' ');
        }
    }
    if (!has_printable) {
        return "";
    }
    while (!bytes.empty() && bytes.back() == ' ') {
        bytes.pop_back();
    }
    return bytes;
}

std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, (last - first + 1));
}

size_t find_matching(const std::string& text, size_t start, char open_char, char close_char) {
    int depth = 0;
    for (size_t i = start; i < text.size(); ++i) {
        if (text[i] == open_char) {
            depth++;
        } else if (text[i] == close_char) {
            depth--;
            if (depth == 0) {
                return i;
            }
        }
    }
    return std::string::npos;
}

std::string extract_json_string(const std::string& object_text, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return "";
    pos = object_text.find(':', pos);
    if (pos == std::string::npos) return "";
    pos = object_text.find('"', pos);
    if (pos == std::string::npos) return "";
    std::string value;
    bool escape = false;
    for (size_t i = pos + 1; i < object_text.size(); ++i) {
        char c = object_text[i];
        if (escape) {
            value += c;
            escape = false;
            continue;
        }
        if (c == '\\') {
            escape = true;
            continue;
        }
        if (c == '"') {
            break;
        }
        value += c;
    }
    return value;
}

std::vector<std::string> parse_json_string_array(const std::string& array_text) {
    std::vector<std::string> result;
    size_t pos = array_text.find('[');
    if (pos == std::string::npos) return result;
    ++pos;
    while (pos < array_text.size()) {
        while (pos < array_text.size() && std::isspace(static_cast<unsigned char>(array_text[pos]))) {
            ++pos;
        }
        if (pos >= array_text.size() || array_text[pos] == ']') {
            break;
        }
        if (array_text[pos] == '"') {
            ++pos;
            std::string value;
            bool escape = false;
            for (; pos < array_text.size(); ++pos) {
                char c = array_text[pos];
                if (escape) {
                    value += c;
                    escape = false;
                    continue;
                }
                if (c == '\\') {
                    escape = true;
                    continue;
                }
                if (c == '"') {
                    ++pos;
                    break;
                }
                value += c;
            }
            result.push_back(value);
            while (pos < array_text.size() && array_text[pos] != ',' && array_text[pos] != ']') {
                ++pos;
            }
            if (pos < array_text.size() && array_text[pos] == ',') {
                ++pos;
            }
        } else {
            while (pos < array_text.size() && array_text[pos] != ',' && array_text[pos] != ']') {
                ++pos;
            }
            if (pos < array_text.size() && array_text[pos] == ',') {
                ++pos;
            }
        }
    }
    return result;
}

std::vector<std::string> extract_json_array(const std::string& object_text, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return {};
    pos = object_text.find('[', pos);
    if (pos == std::string::npos) return {};
    size_t end = find_matching(object_text, pos, '[', ']');
    if (end == std::string::npos) return {};
    std::string array_text = object_text.substr(pos, end - pos + 1);
    return parse_json_string_array(array_text);
}

bool extract_json_bool(const std::string& object_text, const std::string& key, bool default_value) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = object_text.find(pattern);
    if (pos == std::string::npos) return default_value;
    pos = object_text.find(':', pos);
    if (pos == std::string::npos) return default_value;
    ++pos;
    while (pos < object_text.size() && std::isspace(static_cast<unsigned char>(object_text[pos]))) {
        ++pos;
    }
    if (pos >= object_text.size()) return default_value;
    if (object_text.compare(pos, 4, "true") == 0) return true;
    if (object_text.compare(pos, 5, "false") == 0) return false;
    return default_value;
}

}  // namespace fragment
