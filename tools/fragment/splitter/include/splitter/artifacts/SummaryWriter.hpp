#pragma once

#include <fstream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "splitter/artifacts/LibraryScanner.hpp"
#include "splitter/artifacts/SummaryHashCalculator.hpp"
#include "splitter/core/MemorySegment.hpp"
#include "splitter/core/Partition.hpp"
#include "splitter/core/PartitionFiles.hpp"
#include "splitter/support/FlatMap.hpp"
#include "splitter/support/HashService.hpp"

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
    void WriteHeader(std::ofstream& out,
                     const std::string& binary_path,
                     size_t partition_count,
                     size_t parallelizable_count,
                     const std::vector<std::string>& required_libraries,
                     const std::vector<LibraryInfo>& libraries,
                     const std::string& binary_hash,
                     bool can_split,
                     const std::string& memory_hash,
                     const std::string& summary_hash) const;
    void WriteFooter(std::ofstream& out) const;
    void WritePartitions(std::ofstream& out,
                         const std::vector<Partition>& partitions,
                         const std::vector<PartitionFiles>& artifacts,
                         const FlatStringMap& symbol_index) const;
    void WriteMemory(std::ofstream& out, const std::vector<MemorySegment>& memory_segments) const;

    std::string output_dir_;
    std::shared_ptr<const ILibraryScanner> scanner_;
    std::shared_ptr<const SummaryHashCalculator> hash_calculator_;
};

}  // namespace splitter
