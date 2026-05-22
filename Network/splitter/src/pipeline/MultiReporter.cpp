#include "pipeline/MultiReporter.hpp"

namespace splitter {

MultiReporter::MultiReporter(std::vector<std::shared_ptr<IReporter>> reporters)
    : reporters_(std::move(reporters)) {}

void MultiReporter::Banner(const std::string& title) {
    for (auto& r : reporters_)
        r->Banner(title);
}

void MultiReporter::Info(const std::string& message) {
    for (auto& r : reporters_)
        r->Info(message);
}

void MultiReporter::ReportTiming(const std::string& phase, long long milliseconds) {
    for (auto& r : reporters_)
        r->ReportTiming(phase, milliseconds);
}

void MultiReporter::ReportRunStart(const std::string& binary_path, const std::string& output_dir) {
    for (auto& r : reporters_)
        r->ReportRunStart(binary_path, output_dir);
}

void MultiReporter::ReportRunCompleted(int exit_code, long long duration_ms) {
    for (auto& r : reporters_)
        r->ReportRunCompleted(exit_code, duration_ms);
}

void MultiReporter::ReportPhaseStart(const std::string& phase,
                                     const std::vector<std::string>& input_artifacts,
                                     const std::vector<std::string>& output_artifacts) {
    for (auto& r : reporters_)
        r->ReportPhaseStart(phase, input_artifacts, output_artifacts);
}

void MultiReporter::ReportPhaseCompleted(const std::string& phase,
                                         const std::vector<std::string>& input_artifacts,
                                         const std::vector<std::string>& output_artifacts,
                                         long long duration_ms) {
    for (auto& r : reporters_)
        r->ReportPhaseCompleted(phase, input_artifacts, output_artifacts, duration_ms);
}

void MultiReporter::ReportPhaseFailed(const std::string& phase,
                                      const std::vector<std::string>& input_artifacts,
                                      const std::vector<std::string>& output_artifacts,
                                      long long duration_ms,
                                      const std::string& error_message,
                                      int error_code) {
    for (auto& r : reporters_)
        r->ReportPhaseFailed(phase, input_artifacts, output_artifacts, duration_ms, error_message, error_code);
}

void MultiReporter::ReportFunctions(const std::vector<Function>& functions, std::size_t preview) {
    for (auto& r : reporters_)
        r->ReportFunctions(functions, preview);
}

void MultiReporter::ReportLoops(std::vector<Function>& functions, std::size_t preview) {
    for (auto& r : reporters_)
        r->ReportLoops(functions, preview);
}

void MultiReporter::ReportPartition(const Partition& partition, std::size_t sample_preview) {
    for (auto& r : reporters_)
        r->ReportPartition(partition, sample_preview);
}

}  // namespace splitter
