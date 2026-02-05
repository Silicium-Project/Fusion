#pragma once

#include <optional>
#include <ostream>
#include <set>
#include <string>
#include <string_view>
#include <vector>

#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"
#include "core/LibraryInfo.hpp"
#include "core/MemorySegment.hpp"
#include "support/FlatMap.hpp"

namespace splitter {

// Construit le JSON de summary de manière incrémentale.
class SummaryBuilder {
public:
    void SetBinaryInfo(const std::string& binary_path,
                       const std::string& binary_os,
                       const std::string& binary_format,
                       const std::string& binary_hash,
                       const std::string& hash_algo,
                       const std::string& memory_hash,
                       bool can_split,
                       const std::string& summary_hash);

    void SetCounts(std::size_t partition_count, std::size_t parallelizable_count);
    void SetRequiredLibraries(const std::vector<std::string>& libs);

    void SetLibraries(const std::vector<LibraryInfo>& libs);

    void AddPartition(const Partition& partition,
                      const std::optional<PartitionFiles>& files,
                      const std::set<std::string>& required_libraries,
                      const std::string& partition_os,
                      const std::string& partition_format);

    void SetPartitionHashes(const std::vector<std::pair<std::string, std::string>>& hashes);
    void SetMemorySegments(const std::vector<MemorySegment>& segments);

    std::string Build() const;

private:
    std::string header_;
    std::string counts_;
    std::string required_libraries_;
    std::string libraries_;
    std::string partitions_;
    std::string partition_hashes_;
    std::string memory_;
};

}  // namespace splitter
