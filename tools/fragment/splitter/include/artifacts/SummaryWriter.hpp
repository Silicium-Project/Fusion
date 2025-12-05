#pragma once

#include <fstream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "artifacts/LibraryScanner.hpp"
#include "artifacts/SummaryHashCalculator.hpp"
#include "core/MemorySegment.hpp"
#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"
#include "support/FlatMap.hpp"
#include "support/HashService.hpp"

namespace splitter {

class SummaryWriter {
public:
    SummaryWriter(std::string output_dir,
                  std::shared_ptr<const ILibraryScanner> scanner,
                  std::shared_ptr<const SummaryHashCalculator> hash_calculator = nullptr);
    SummaryWriter(std::string output_dir,
                  std::shared_ptr<const ILibraryScanner> scanner,
                  HashService hash_service);

    void Write(const std::vector<Partition>& partitions,
               const std::vector<PartitionFiles>& artifacts,
               const std::vector<MemorySegment>& memory_segments,
               const std::string& binary_path) const;

private:
    bool OpenSummaryFile(const std::string& path, std::ofstream& out) const;

    std::string output_dir_;
    std::shared_ptr<const ILibraryScanner> scanner_;
    std::shared_ptr<const SummaryHashCalculator> hash_calculator_;
};

}  // namespace splitter
