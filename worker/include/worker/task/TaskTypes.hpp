#pragma once

#include <cstdint>
#include <map>
#include <string>

namespace worker {

using PartitionId = std::string;
using RegisterValue = std::uint64_t;
using RegisterState = std::map<std::string, RegisterValue>;

}  // namespace worker
