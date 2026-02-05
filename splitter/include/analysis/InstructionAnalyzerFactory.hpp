#pragma once

#include <memory>
#include <string>

#include "analysis/CompositeInstructionAnalyzer.hpp"
#include "support/SystemContext.hpp"

namespace splitter {

class InstructionAnalyzerFactory {
public:
    static CompositeInstructionAnalyzer Create(const std::string& arch_name);
    static CompositeInstructionAnalyzer CreateDefault();
    static CompositeInstructionAnalyzer CreateDefault(const SystemContext& system);
};

}  // namespace splitter
