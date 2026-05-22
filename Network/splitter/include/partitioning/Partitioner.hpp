#pragma once

#include <memory>
#include <string>
#include <vector>

#include "analysis/IInstructionAnalyzer.hpp"
#include "partitioning/BinaryExtractor.hpp"
#include "partitioning/IPartitioner.hpp"
#include "partitioning/PartitionGraphBuilder.hpp"
#include "pipeline/BinaryPath.hpp"
#include "core/Partition.hpp"
#include "support/HashService.hpp"

namespace splitter {

class Partitioner : public IPartitioner {
public:
    Partitioner(BinaryPath binary_path,
                std::shared_ptr<const IInstructionAnalyzer> analyzer,
                std::shared_ptr<BinaryExtractor> extractor,
                HashService hash_service = HashService());

    std::vector<Partition> Run(std::vector<Function>& functions) override;

private:
    BinaryPath binary_path_;
    std::shared_ptr<const IInstructionAnalyzer> analyzer_;
    std::shared_ptr<BinaryExtractor> extractor_;
    DefaultPartitionGraphBuilder graph_builder_;
};

}  // namespace splitter
