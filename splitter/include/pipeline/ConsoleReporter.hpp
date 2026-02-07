#pragma once

#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "pipeline/IReporter.hpp"
#include "core/Function.hpp"
#include "core/Partition.hpp"

namespace splitter {

class ConsoleReporter : public IReporter {
public:
    enum class Color { Green, Cyan, Yellow, Reset };

    ConsoleReporter() = default;

    void Banner(const std::string& title) override;
    void Info(const std::string& message) override;
    void ReportTiming(const std::string& phase, long long milliseconds) override;
    void ReportFunctions(const std::vector<Function>& functions, std::size_t preview) override;
    void ReportLoops(std::vector<Function>& functions, std::size_t preview) override;
    void ReportPartition(const Partition& partition, std::size_t sample_preview) override;

private:
    template <typename Container>
    void PrintSample(const std::string& label, const Container& container, std::size_t limit);

    std::string Colorize(const std::string& text, Color color) const;
};

}  // namespace splitter
