#pragma once

#include <stdexcept>
#include <string>

namespace splitter {

enum class PipelineExit {
    Ok = 0,
    DisassemblyError = 2,
    AnalysisError = 3,
    PartitioningError = 4,
    ArtifactsError = 5,
    IoError = 6,
    UnknownError = 1,
};

class PipelineError : public std::runtime_error {
public:
    PipelineError(std::string phase, std::string message, PipelineExit code = PipelineExit::UnknownError);

    const std::string& Phase() const noexcept;
    PipelineExit Code() const noexcept;

private:
    std::string phase_;
    PipelineExit code_;
};

}  // namespace splitter
