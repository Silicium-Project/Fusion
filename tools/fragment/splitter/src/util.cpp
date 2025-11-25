#include "splitter/util.hpp"

#include <array>
#include <cstdio>
#include <cstring>
#include <memory>
#include <set>
#include <sstream>
#include <fstream>
#include <functional>
#include <iomanip>
#include <cstdint>

namespace splitter {

    std::string json_escape(const std::string& input) {
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

    std::string exec_command(const std::string& cmd) {
        std::array<char, 128> buffer;
        std::string result;
        auto closer = [](FILE* fp) {
            if (fp)
                pclose(fp);
        };
        std::unique_ptr<FILE, decltype(closer)> pipe(popen(cmd.c_str(), "r"), closer);

        if (!pipe)
            throw std::runtime_error("popen() failed");

        while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr)
            result += buffer.data();
        return result;
    }

    std::vector<std::string> split_string(const std::string& str, char delimiter) {
        std::vector<std::string> tokens;
        std::stringstream ss(str);
        std::string token;

        while (std::getline(ss, token, delimiter))
            tokens.push_back(token);
        return tokens;
    }

    std::string trim(const std::string& str) {
        size_t first = str.find_first_not_of(" \t\r\n");

        if (first == std::string::npos)
            return "";

        size_t last = str.find_last_not_of(" \t\r\n");

        return str.substr(first, last - first + 1);
    }

    std::string vector_to_json(const std::vector<std::string>& values) {
        std::ostringstream oss;
        oss << "[";
        for (size_t i = 0; i < values.size(); ++i) {
            if (i)
                oss << ", ";
            oss << '"' << json_escape(values[i]) << '"';
        }
        oss << "]";
        return oss.str();
    }

    std::string set_to_json(const std::set<std::string>& values) {
        std::vector<std::string> vectorized(values.begin(), values.end());

        return vector_to_json(vectorized);
    }

    std::string hash_bytes(const std::vector<uint8_t>& data) {
        // Fallback hash (non cryptographique) pour éviter d'ajouter une dépendance.
        std::hash<std::string_view> hasher;
        std::string_view view(reinterpret_cast<const char*>(data.data()), data.size());
        auto value = hasher(view);
        std::ostringstream oss;
        oss << std::hex << std::setw(16) << std::setfill('0') << value;
        return oss.str();
    }

    std::string hash_file(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file.is_open())
            return {};
        std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                    std::istreambuf_iterator<char>());
        return hash_bytes(buffer);
    }

    std::string hash_string(const std::string& data) {
        std::hash<std::string_view> hasher;
        auto value = hasher(std::string_view(data));
        std::ostringstream oss;
        oss << std::hex << std::setw(16) << std::setfill('0') << value;
        return oss.str();
    }

}  // namespace splitter
