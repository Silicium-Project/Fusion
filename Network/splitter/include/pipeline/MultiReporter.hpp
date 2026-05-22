#pragma once

#include <memory>
#include <vector>

#include "pipeline/IReporter.hpp"

namespace splitter {

class MultiReporter : public IReporter {
public:
    explicit MultiReporter(std::vector<std::shared_ptr<IReporter>> reporters);

    void Banner(const std::string& title) override;
    void Info(const std::string& message) override;
    void ReportTiming(const std::string& phase, long long milliseconds) override;
    void ReportRunStart(const std::string& binary_path, const std::string& output_dir) override;
    void ReportRunCompleted(int exit_code, long long duration_ms) override;
    void ReportPhaseStart(const std::string& phase,
                          const std::vector<std::string>& input_artifacts,
                          const std::vector<std::string>& output_artifacts) override;
    void ReportPhaseCompleted(const std::string& phase,
                              const std::vector<std::string>& input_artifacts,
                              const std::vector<std::string>& output_artifacts,
                              long long duration_ms) override;
    void ReportPhaseFailed(const std::string& phase,
                           const std::vector<std::string>& input_artifacts,
                           const std::vector<std::string>& output_artifacts,
                           long long duration_ms,
                           const std::string& error_message,
                           int error_code) override;
    void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) override;
    void ReportLoops(std::vector<Function>& functions, std::size_t preview) override;
    void ReportPartition(const Partition& partition, std::size_t sample_preview) override;

private:
    std::vector<std::shared_ptr<IReporter>> reporters_;
};

}  // namespace splitter
