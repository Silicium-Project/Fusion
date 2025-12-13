#pragma once

#include <memory>
#include <string>

#include "analysis/CompositeInstructionAnalyzer.hpp"

namespace splitter {

class InstructionAnalyzerFactory {
public:
    static CompositeInstructionAnalyzer Create(const std::string& arch_name);
    static CompositeInstructionAnalyzer CreateDefault();
};

}  // namespace splitter
