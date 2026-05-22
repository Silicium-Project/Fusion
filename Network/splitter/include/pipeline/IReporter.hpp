#pragma once

#include <string>
#include <vector>

#include "core/Function.hpp"
#include "core/Partition.hpp"

namespace splitter {

class IReporter {
public:
    virtual ~IReporter() = default;

    virtual void Banner(const std::string& title) = 0;
    virtual void Info(const std::string& message) = 0;
    virtual void ReportTiming(const std::string& phase, long long milliseconds) = 0;
    virtual void ReportRunStart(const std::string& binary_path, const std::string& output_dir) {
        (void)binary_path;
        (void)output_dir;
    }
    virtual void ReportRunCompleted(int exit_code, long long duration_ms) {
        (void)exit_code;
        (void)duration_ms;
    }
    virtual void ReportPhaseStart(const std::string& phase,
                                  const std::vector<std::string>& input_artifacts,
                                  const std::vector<std::string>& output_artifacts) {
        (void)phase;
        (void)input_artifacts;
        (void)output_artifacts;
    }
    virtual void ReportPhaseCompleted(const std::string& phase,
                                      const std::vector<std::string>& input_artifacts,
                                      const std::vector<std::string>& output_artifacts,
                                      long long duration_ms) {
        (void)phase;
        (void)input_artifacts;
        (void)output_artifacts;
        (void)duration_ms;
    }
    virtual void ReportPhaseFailed(const std::string& phase,
                                   const std::vector<std::string>& input_artifacts,
                                   const std::vector<std::string>& output_artifacts,
                                   long long duration_ms,
                                   const std::string& error_message,
                                   int error_code = -1) {
        (void)phase;
        (void)input_artifacts;
        (void)output_artifacts;
        (void)duration_ms;
        (void)error_message;
        (void)error_code;
    }

    virtual void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) = 0;
    virtual void ReportLoops(std::vector<Function>& functions, std::size_t preview) = 0;
    virtual void ReportPartition(const Partition& partition, std::size_t sample_preview) = 0;
};

}  // namespace splitter
