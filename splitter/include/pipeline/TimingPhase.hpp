#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <iostream>

#include "pipeline/IPipelinePhase.hpp"
#include "pipeline/IReporter.hpp"

namespace splitter {

// Décorateur simple qui mesure la durée d'exécution d'une phase et logge le résultat.
class TimingPhase : public IPipelinePhase {
public:
    explicit TimingPhase(std::unique_ptr<IPipelinePhase> inner, std::shared_ptr<IReporter> reporter = {});

    std::string Name() const override;
    void Execute(PipelineContext& context) override;
    std::vector<std::string> Inputs() const override;
    std::vector<std::string> Outputs() const override;

private:
    std::unique_ptr<IPipelinePhase> inner_;
    std::shared_ptr<IReporter> reporter_;
};

}  // namespace splitter
