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
    void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) override;
    void ReportLoops(std::vector<Function>& functions, std::size_t preview) override;
    void ReportPartition(const Partition& partition, std::size_t sample_preview) override;

private:
    std::vector<std::shared_ptr<IReporter>> reporters_;
};

}  // namespace splitter
