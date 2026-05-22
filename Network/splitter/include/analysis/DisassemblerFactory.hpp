#pragma once

#include <memory>
#include <string>

#include "analysis/IDisassembler.hpp"
#include "pipeline/PipelineConfig.hpp"
#include "support/SystemContext.hpp"

namespace splitter {

class DisassemblerFactory {
public:
    static std::unique_ptr<IDisassembler> Create(const PipelineConfig& config,
                                                 const SystemContext& system);
    static std::unique_ptr<IDisassembler> CreateDefault(const PipelineConfig& config);
};

}  // namespace splitter
