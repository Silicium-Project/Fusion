#pragma once

#include <string>

namespace splitter {

class LoopAnalysis {
public:
    bool parallelizable = false;
    std::string reason;
};

}  // namespace splitter
