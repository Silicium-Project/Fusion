#include "cli/SplitterCli.hpp"

#include "pipeline/PipelineRunner.hpp"
#include "support/HashUtil.hpp"

namespace splitter {

int SplitterCli::Run(const std::vector<std::string_view>& args) {
    // Appliquer la config de hash (env ou option CLI avant parsing détaillé).
    SetGlobalHashService(MakeHashServiceFromEnv());
    return RunCli(args);
}

}  // namespace splitter
