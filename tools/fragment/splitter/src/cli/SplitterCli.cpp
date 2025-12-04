#include "splitter/cli/SplitterCli.hpp"

#include "splitter/pipeline/PipelineRunner.hpp"

namespace splitter {

int SplitterCli::Run(const std::vector<std::string_view>& args) {
    return RunCli(args);
}

}  // namespace splitter
