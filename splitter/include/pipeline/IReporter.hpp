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

    virtual void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) = 0;
    virtual void ReportLoops(std::vector<Function>& functions, std::size_t preview) = 0;
    virtual void ReportPartition(const Partition& partition, std::size_t sample_preview) = 0;
};

}  // namespace splitter
