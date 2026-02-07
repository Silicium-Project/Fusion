#include "analysis/InstructionAnalyzerFactory.hpp"

#include <algorithm>
#include <functional>
#include <string_view>
#include <vector>

#include "analysis/ArmInstructionAnalyzer.hpp"
#include "analysis/GuiInstructionAnalyzer.hpp"
#include "analysis/RiscVInstructionAnalyzer.hpp"
#include "analysis/X86_64InstructionAnalyzer.hpp"

namespace splitter {

namespace {

std::string NormalizeArch(std::string_view arch) {
    std::string lowered(arch);
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return lowered;
}

struct AnalyzerHandler {
    std::function<bool(const std::string&)> matches;
    std::function<CompositeInstructionAnalyzer()> builder;
};

template <typename... Analyzers>
CompositeInstructionAnalyzer MakeComposite() {
    CompositeInstructionAnalyzer composite;
    (composite.AddAnalyzer(Analyzers::Instance()), ...);
    return composite;
}

[[maybe_unused]] AnalyzerHandler MakeExactHandler(std::vector<std::string> aliases,
                                                  std::function<CompositeInstructionAnalyzer()> builder) {
    return {
        [aliases = std::move(aliases)](const std::string& arch) {
            return std::any_of(aliases.begin(), aliases.end(),
                               [&](const std::string& alias) { return arch == alias; });
        },
        std::move(builder),
    };
}

AnalyzerHandler MakeContainsHandler(std::vector<std::string> tokens,
                                    std::function<CompositeInstructionAnalyzer()> builder) {
    return {
        [tokens = std::move(tokens)](const std::string& arch) {
            return std::any_of(tokens.begin(), tokens.end(),
                               [&](const std::string& token) { return arch.find(token) != std::string::npos; });
        },
        std::move(builder),
    };
}

std::vector<AnalyzerHandler> BuildHandlers() {
    return {
        MakeContainsHandler({"x86_64", "x86-64", "amd64", "x64", "i386"},
                            &MakeComposite<X86_64InstructionAnalyzer, GuiInstructionAnalyzer>),
        MakeContainsHandler({"arm", "aarch64"},
                            &MakeComposite<ArmInstructionAnalyzer, GuiInstructionAnalyzer>),
        MakeContainsHandler({"riscv", "risc-v"},
                            &MakeComposite<RiscVInstructionAnalyzer, GuiInstructionAnalyzer>),
    };
}

}  // namespace

CompositeInstructionAnalyzer InstructionAnalyzerFactory::Create(const std::string& arch_name) {
    const std::string normalized = NormalizeArch(arch_name);
    static const std::vector<AnalyzerHandler> handlers = BuildHandlers();
    for (const auto& handler : handlers) {
        if (handler.matches(normalized)) {
            return handler.builder();
        }
    }
    // Fallback minimal analyzer set; extend the handler list for new architectures.
    return MakeComposite<GuiInstructionAnalyzer>();
}

CompositeInstructionAnalyzer InstructionAnalyzerFactory::CreateDefault() {
    return CreateDefault(DefaultSystemContext());
}

CompositeInstructionAnalyzer InstructionAnalyzerFactory::CreateDefault(const SystemContext& system) {
    if (system.env) {
        if (auto env = system.env->Get("SPLITTER_ARCH"))
            return Create(*env);
    }

    // Déduire l'architecture via uname -m (sans préprocesseur).
    if (system.shell) {
        try {
            std::string arch_hint = system.shell->Run("uname -m");
            // nettoyer fin de ligne
            arch_hint.erase(std::remove_if(arch_hint.begin(), arch_hint.end(),
                                           [](unsigned char c) { return c == '\n' || c == '\r'; }),
                            arch_hint.end());
            if (!arch_hint.empty())
                return Create(arch_hint);
        } catch (const std::exception&) {
            // ignore et fallback
        }
    }
    return Create("generic");
}

}  // namespace splitter
