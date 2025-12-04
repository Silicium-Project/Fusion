#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "splitter/core/MemorySegment.hpp"

namespace splitter {

class BinaryExtractor {
public:
    virtual ~BinaryExtractor();

    virtual std::vector<uint8_t> ExtractSegment(const std::string& binary_path,
                                                uint64_t start_addr,
                                                uint64_t end_addr) const;

    virtual std::vector<MemorySegment> ExtractDataSections(const std::string& binary_path) const;
};

}  // namespace splitter
