#pragma once

#include <set>
#include <string>
#include <utility>
#include <vector>

#include "splitter/artifacts/HashAlgorithm.hpp"
#include "splitter/artifacts/FnvHashAlgorithm.hpp"
#include "splitter/core/LibraryInfo.hpp"
#include "splitter/core/MemorySegment.hpp"
#include "splitter/core/Partition.hpp"
#include "splitter/support/FnvHasher.hpp"
#include "splitter/support/HashService.hpp"

namespace splitter {

class SummaryHashCalculator {
public:
    explicit SummaryHashCalculator(std::shared_ptr<IHashAlgorithm> algorithm = nullptr,
                                   HashService hash_service = HashService());
    explicit SummaryHashCalculator(std::shared_ptr<IHashAlgorithm> algorithm);
    explicit SummaryHashCalculator(HashService hash_service);

    std::string ComputePartitionHash(const Partition& partition,
                                     const std::set<std::string>& resolved_libs) const;
    std::string ComputeMemoryHash(const std::vector<MemorySegment>& segments) const;
    std::string ComputeSummaryHash(const std::string& binary_hash,
                                   const std::string& memory_hash,
                                   bool can_split,
                                   const std::vector<std::string>& required_libraries,
                                   const std::vector<LibraryInfo>& libraries,
                                   const std::vector<std::pair<std::string, std::string>>& partition_hashes) const;
    std::unique_ptr<IHashAlgorithm> make_hash() const;

    std::shared_ptr<IHashAlgorithm> algorithm_;
    HashService hash_service_;
};

}  // namespace splitter
