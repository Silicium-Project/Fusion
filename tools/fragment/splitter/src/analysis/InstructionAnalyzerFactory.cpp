#include "analysis/InstructionAnalyzerFactory.hpp"

#include <algorithm>
#include <string_view>

#include "analysis/GuiInstructionAnalyzer.hpp"
#include "analysis/X86_64InstructionAnalyzer.hpp"
#include "support/Env.hpp"

namespace splitter {

namespace {

std::string NormalizeArch(std::string_view arch) {
    std::string lowered(arch);
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return lowered;
}

void AddX86_64Analyzers(CompositeInstructionAnalyzer& composite) {
    composite.AddAnalyzer(X86_64InstructionAnalyzer::Instance());
    composite.AddAnalyzer(GuiInstructionAnalyzer::Instance());
}

}  // namespace

CompositeInstructionAnalyzer InstructionAnalyzerFactory::Create(const std::string& arch_name) {
    CompositeInstructionAnalyzer composite;
    const std::string normalized = NormalizeArch(arch_name);
    if (normalized == "x86_64" || normalized == "x86-64" || normalized == "amd64" || normalized == "x64") {
        AddX86_64Analyzers(composite);
    } else {
        // Fallback minimal analyzer set; extend here for new architectures.
        composite.AddAnalyzer(GuiInstructionAnalyzer::Instance());
    }
    return composite;
}

CompositeInstructionAnalyzer InstructionAnalyzerFactory::CreateDefault() {
    if (auto env = GetEnv("SPLITTER_ARCH"))
        return Create(*env);
#if defined(__x86_64__) || defined(_M_X64)
    return Create("x86_64");
#else
    return Create("generic");
#endif
}

}  // namespace splitter
