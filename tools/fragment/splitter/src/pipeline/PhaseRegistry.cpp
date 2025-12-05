#include "pipeline/PhaseRegistry.hpp"

#include <stdexcept>

namespace splitter {

void PhaseRegistry::Register(const std::string& name, Builder builder) {
    builders_[name] = std::move(builder);
}

std::unique_ptr<IPipelinePhase> PhaseRegistry::Create(const std::string& name) const {
    auto it = builders_.find(name);
    if (it == builders_.end())
        throw std::runtime_error("Phase inconnue: " + name);
    return it->second();
}

std::vector<std::unique_ptr<IPipelinePhase>> PhaseRegistry::CreateSequence(
    const std::vector<std::string>& names) const {
    std::vector<std::unique_ptr<IPipelinePhase>> phases;
    phases.reserve(names.size());
    for (const auto& n : names)
        phases.push_back(Create(n));
    return phases;
}

}  // namespace splitter
