#pragma once

#include <iostream>
#include <memory>
#include <ostream>
#include <string>
#include <vector>

#include "pipeline/IReporter.hpp"

namespace splitter {

class JsonReporter : public IReporter {
public:
    explicit JsonReporter(std::shared_ptr<std::ostream> out = {});

    void Banner(const std::string& title) override;
    void Info(const std::string& message) override;
    void ReportTiming(const std::string& phase, long long milliseconds) override;

    void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) override;
    void ReportLoops(std::vector<Function>& functions, std::size_t preview) override;
    void ReportPartition(const Partition& partition, std::size_t sample_preview) override;

private:
    std::shared_ptr<std::ostream> out_;
    void WriteKeyValue(const std::string& key, const std::string& value);
};

}  // namespace splitter
