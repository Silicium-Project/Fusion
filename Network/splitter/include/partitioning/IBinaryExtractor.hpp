#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "core/MemorySegment.hpp"

namespace splitter {

class IBinaryExtractor {
public:
    virtual ~IBinaryExtractor() = default;
    virtual std::vector<uint8_t> ExtractSegment(const std::string& binary_path,
                                                uint64_t start_addr,
                                                uint64_t end_addr) const = 0;
    virtual std::vector<MemorySegment> ExtractDataSections(const std::string& binary_path) const = 0;
};

}  // namespace splitter
