#include "pipeline/PipelineError.hpp"

namespace splitter {

PipelineError::PipelineError(std::string phase, std::string message, PipelineExit code)
: std::runtime_error(std::move(message)), phase_(std::move(phase)), code_(code) {}

const std::string& PipelineError::Phase() const noexcept {
    return phase_;
}

PipelineExit PipelineError::Code() const noexcept {
    return code_;
}

}  // namespace splitter
