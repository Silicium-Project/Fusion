#pragma once

#include <memory>

#include "splitter/pipeline/PipelineRunner.hpp"

namespace splitter {

class PipelineFactory {
public:
    static std::unique_ptr<PipelineRunner> BuildDefault(PipelineConfig config);
};

}  // namespace splitter
