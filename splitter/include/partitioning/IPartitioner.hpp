#pragma once

#include <vector>

#include "core/Partition.hpp"

namespace splitter {

class IPartitioner {
public:
    virtual ~IPartitioner() = default;
    virtual std::vector<Partition> Run(std::vector<Function>& functions) = 0;
};

}  // namespace splitter
