#pragma once

#include "splitter/pipeline/PipelineContext.hpp"

namespace splitter {

class IPipelinePhase {
public:
    virtual ~IPipelinePhase() = default;
    virtual const char* Name() const = 0;
    virtual void Execute(PipelineContext& context) = 0;
};

}  // namespace splitter
