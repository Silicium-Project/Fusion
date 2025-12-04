#pragma once

#include <memory>
#include <string>
#include <vector>

#include "splitter/analysis/IInstructionAnalyzer.hpp"
#include "splitter/partitioning/BinaryExtractor.hpp"
#include "splitter/partitioning/IPartitioner.hpp"
#include "splitter/pipeline/Paths.hpp"
#include "splitter/core/Partition.hpp"

namespace splitter {

class Partitioner : public IPartitioner {
public:
    Partitioner(BinaryPath binary_path, const IInstructionAnalyzer& analyzer, const BinaryExtractor& extractor);

    std::vector<Partition> Run(std::vector<Function>& functions) override;

private:
    BinaryPath binary_path_;
    const IInstructionAnalyzer& analyzer_;
    const BinaryExtractor& extractor_;
};

}  // namespace splitter
