#pragma once

#include <string>
#include <utility>
#include <vector>

#include "splitter/core/Function.hpp"

namespace splitter {

class IDisassembler {
public:
    virtual ~IDisassembler() = default;

    virtual std::pair<std::vector<Function>, std::string> Run() const = 0;
};

}  // namespace splitter
