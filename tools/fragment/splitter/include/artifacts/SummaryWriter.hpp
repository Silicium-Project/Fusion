#pragma once

#include <filesystem>
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
    SummaryWriter(std::filesystem::path output_dir,
                  std::shared_ptr<const ILibraryScanner> scanner,
                  std::shared_ptr<const SummaryHashCalculator> hash_calculator = nullptr);
    SummaryWriter(std::filesystem::path output_dir,
                  std::shared_ptr<const ILibraryScanner> scanner,
                  HashService hash_service);

    void Write(const std::vector<Partition>& partitions,
               const std::vector<PartitionFiles>& artifacts,
               const std::vector<MemorySegment>& memory_segments,
               const std::filesystem::path& binary_path) const;

private:
    bool OpenSummaryFile(const std::filesystem::path& path, std::ofstream& out) const;

    std::filesystem::path output_dir_;
    std::shared_ptr<const ILibraryScanner> scanner_;
    std::shared_ptr<const SummaryHashCalculator> hash_calculator_;
};

}  // namespace splitter
