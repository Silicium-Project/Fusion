#pragma once

#include <functional>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "pipeline/IPipelinePhase.hpp"

namespace splitter {

class PhaseRegistry {
public:
    using Builder = std::function<std::unique_ptr<IPipelinePhase>()>;

    void Register(const std::string& name, Builder builder);
    std::unique_ptr<IPipelinePhase> Create(const std::string& name) const;
    std::vector<std::unique_ptr<IPipelinePhase>> CreateSequence(
        const std::vector<std::string>& names) const;

private:
    std::unordered_map<std::string, Builder> builders_;
};

}  // namespace splitter
