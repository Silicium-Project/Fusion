#pragma once

#include <string>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions,
                                              const std::string& binary_path);
std::vector<uint8_t> extract_binary_segment(const std::string& binary_path,
                                            uint64_t start_addr, uint64_t end_addr);
std::string function_to_asm(const Function& func);

}  // namespace splitter
