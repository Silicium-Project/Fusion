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
