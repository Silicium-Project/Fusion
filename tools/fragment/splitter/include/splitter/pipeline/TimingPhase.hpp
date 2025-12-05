#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <iostream>

#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

// Décorateur simple qui mesure la durée d'exécution d'une phase et logge le résultat.
class TimingPhase : public IPipelinePhase {
public:
    explicit TimingPhase(std::unique_ptr<IPipelinePhase> inner)
        : inner_(std::move(inner)) {}

    std::string Name() const override { return inner_->Name(); }

    void Execute(PipelineContext& context) override {
        using clock = std::chrono::steady_clock;
        auto start = clock::now();
        inner_->Execute(context);
        auto end = clock::now();
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
        std::cout << "[" << Name() << "] " << ms << " ms\n";
    }

private:
    std::unique_ptr<IPipelinePhase> inner_;
};

}  // namespace splitter
