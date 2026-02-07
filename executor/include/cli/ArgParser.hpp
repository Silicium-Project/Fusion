#pragma once

#include "cli/Cli.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace fragment {

CliOptions parse_arguments(const std::vector<std::string_view>& args);

}  // namespace fragment
