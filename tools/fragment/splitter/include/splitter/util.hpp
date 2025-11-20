#pragma once

#include <set>
#include <string>
#include <vector>

namespace splitter {

    std::string json_escape(const std::string& input);
    std::string trim(const std::string& str);
    std::vector<std::string> split_string(const std::string& str, char delimiter);
    std::string exec_command(const std::string& cmd);

    std::string vector_to_json(const std::vector<std::string>& values);
    std::string set_to_json(const std::set<std::string>& values);

}  // namespace splitter
