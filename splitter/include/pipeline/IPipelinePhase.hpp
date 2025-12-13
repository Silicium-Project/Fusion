#pragma once

#include <string>

#include "pipeline/PipelineContext.hpp"

namespace splitter {

class IPipelinePhase {
public:
    virtual ~IPipelinePhase() = default;
    virtual std::string Name() const = 0;
    virtual void Execute(PipelineContext& context) = 0;
};

}  // namespace splitter
