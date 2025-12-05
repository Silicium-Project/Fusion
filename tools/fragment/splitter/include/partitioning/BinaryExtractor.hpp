#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "core/MemorySegment.hpp"
#include "partitioning/IBinaryExtractor.hpp"

namespace splitter {

class BinaryExtractor : public IBinaryExtractor {
public:
    virtual ~BinaryExtractor();

    std::vector<uint8_t> ExtractSegment(const std::string& binary_path,
                                        uint64_t start_addr,
                                        uint64_t end_addr) const override;

    std::vector<MemorySegment> ExtractDataSections(const std::string& binary_path) const override;
};

}  // namespace splitter
