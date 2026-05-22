#pragma once

#include <memory>

#include "pipeline/IReporter.hpp"
#include "pipeline/PipelineConfig.hpp"

namespace splitter {

class ReporterFactory {
public:
    static std::shared_ptr<IReporter> Create(const PipelineConfig& config);
};

}  // namespace splitter
