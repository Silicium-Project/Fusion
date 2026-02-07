#include "analysis/DisassemblerFactory.hpp"

#include <algorithm>
#include <stdexcept>

#include "analysis/ObjdumpDisassembler.hpp"

namespace splitter {

namespace {

std::string NormalizeChoice(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}

}  // namespace

std::unique_ptr<IDisassembler> DisassemblerFactory::Create(const PipelineConfig& config,
                                                            const SystemContext& system) {
    std::string choice = config.disassembler;
    if (choice.empty() && system.env) {
        if (auto env = system.env->Get("SPLITTER_DISASSEMBLER"))
            choice = *env;
    }
    choice = NormalizeChoice(choice);
    if (choice.empty() || choice == "objdump")
        return std::make_unique<ObjdumpDisassembler>(config.binary_path.Value(), system);
    throw std::runtime_error("Désassembleur inconnu: " + choice);
}

std::unique_ptr<IDisassembler> DisassemblerFactory::CreateDefault(const PipelineConfig& config) {
    return Create(config, DefaultSystemContext());
}

}  // namespace splitter
