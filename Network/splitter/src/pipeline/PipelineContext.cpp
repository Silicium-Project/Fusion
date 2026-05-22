#include "pipeline/PipelineContext.hpp"

namespace splitter {

PipelineContext::PipelineContext(PipelineConfig config)
: config(std::move(config)) {}

}  // namespace splitter
