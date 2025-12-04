#pragma once

#include <memory>
#include <string>
#include <vector>

#include "splitter/analysis/IInstructionAnalyzer.hpp"
#include "splitter/partitioning/BinaryExtractor.hpp"
#include "splitter/partitioning/IPartitioner.hpp"
#include "splitter/partitioning/PartitionGraphBuilder.hpp"
#include "splitter/pipeline/Paths.hpp"
#include "splitter/core/Partition.hpp"
#include "splitter/support/HashService.hpp"

namespace splitter {

class Partitioner : public IPartitioner {
public:
    Partitioner(BinaryPath binary_path,
                const IInstructionAnalyzer& analyzer,
                const BinaryExtractor& extractor,
                HashService hash_service = HashService());

    std::vector<Partition> Run(std::vector<Function>& functions) override;

private:
    BinaryPath binary_path_;
    const IInstructionAnalyzer& analyzer_;
    const BinaryExtractor& extractor_;
    DefaultPartitionGraphBuilder graph_builder_;
};

}  // namespace splitter
