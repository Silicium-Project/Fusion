#pragma once

#include <string_view>
#include <vector>

namespace splitter {

class SplitterCli {
public:
    static int Run(const std::vector<std::string_view>& args);
};

}  // namespace splitter
