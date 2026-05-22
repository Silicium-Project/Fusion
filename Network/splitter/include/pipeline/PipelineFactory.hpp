#pragma once

#include <memory>

#include "pipeline/PipelineRunner.hpp"

namespace splitter {

class PipelineFactory {
public:
    static std::unique_ptr<PipelineRunner> BuildDefault(PipelineConfig config);

    // Fabrique générique permettant d'injecter des phases custom via des fonctions ou lambdas.
    template <typename DisasmFactory, typename AnalysisFactory, typename PartitionFactory, typename ArtifactFactory>
    static std::unique_ptr<PipelineRunner> BuildCustom(PipelineConfig config,
                                                       DisasmFactory make_disasm,
                                                       AnalysisFactory make_analysis,
                                                       PartitionFactory make_partition,
                                                       ArtifactFactory make_artifacts) {
        auto disassembly = make_disasm(config);
        auto analysis = make_analysis(config);
        auto partitioning = make_partition(config);
        auto artifacts = make_artifacts(config);
        return std::make_unique<PipelineRunner>(std::move(config), std::move(disassembly), std::move(analysis),
                                                std::move(partitioning), std::move(artifacts));
    }
};

}  // namespace splitter
