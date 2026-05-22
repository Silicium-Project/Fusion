#pragma once

#include <string>
#include <vector>

#include "pipeline/PipelineContext.hpp"

namespace splitter {

class IPipelinePhase {
public:
    virtual ~IPipelinePhase() = default;
    virtual std::string Name() const = 0;
    virtual void Execute(PipelineContext& context) = 0;
    virtual std::vector<std::string> Inputs() const { return {}; }
    virtual std::vector<std::string> Outputs() const { return {}; }
};

}  // namespace splitter
