#include "pipeline/TimingPhase.hpp"

#include <chrono>
#include <iostream>

namespace splitter {

TimingPhase::TimingPhase(std::unique_ptr<IPipelinePhase> inner, std::shared_ptr<IReporter> reporter)
: inner_(std::move(inner)), reporter_(std::move(reporter)) {}

std::string TimingPhase::Name() const {
    return inner_->Name();
}

std::vector<std::string> TimingPhase::Inputs() const {
    return inner_->Inputs();
}

std::vector<std::string> TimingPhase::Outputs() const {
    return inner_->Outputs();
}

void TimingPhase::Execute(PipelineContext& context) {
    using clock = std::chrono::steady_clock;
    auto start = clock::now();
    inner_->Execute(context);
    auto end = clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    if (reporter_)
        reporter_->ReportTiming(Name(), ms);
    else
        std::cout << "[" << Name() << "] " << ms << " ms\n";
}

}  // namespace splitter
