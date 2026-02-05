#include "artifacts/SummaryHashCalculator.hpp"
#include "artifacts/FnvHashAlgorithm.hpp"
#include "artifacts/StdHashAlgorithm.hpp"

#include <algorithm>

#include "support/HashUtil.hpp"

namespace splitter {

namespace {

template <typename Container>
void HashStrings(IHashAlgorithm& h, const Container& c) {
    for (const auto& s : c)
        h.AddString(s);
    h.AddByte(0x7f);
}

}  // namespace

SummaryHashCalculator::SummaryHashCalculator(std::shared_ptr<IHashAlgorithm> algorithm, HashService hash_service)
    : algorithm_(std::move(algorithm)),
      hash_service_(std::move(hash_service)) {}

SummaryHashCalculator::SummaryHashCalculator(std::shared_ptr<IHashAlgorithm> algorithm)
    : SummaryHashCalculator(std::move(algorithm), HashService()) {}

SummaryHashCalculator::SummaryHashCalculator(HashService hash_service)
    : SummaryHashCalculator(nullptr, std::move(hash_service)) {}

std::unique_ptr<IHashAlgorithm> SummaryHashCalculator::make_hash() const {
    if (algorithm_)
        return algorithm_->Clone();
    return hash_service_.CreateHasher();
}

std::string SummaryHashCalculator::ComputePartitionHash(
    const Partition& p,
    const std::set<std::string>& resolved_libs,
    const std::string& partition_os,
    const std::string& partition_format) const {
    auto hasher = make_hash();
    hasher->Reset();
    hasher->AddString(p.Id());
    if (!partition_os.empty())
        hasher->AddString(partition_os);
    if (!partition_format.empty())
        hasher->AddString(partition_format);
    hasher->AddUint64(p.StartAddr());
    hasher->AddUint64(p.EndAddr());
    hasher->AddString(p.BinHash());
    hasher->AddUint64(p.RawBytes().size());
    hasher->AddBool(p.IsParallelizable());
    hasher->AddBool(p.RequiresDisplay());
    HashStrings(*hasher, p.Inputs());
    HashStrings(*hasher, p.ExternalInputs());
    HashStrings(*hasher, p.Outputs());
    HashStrings(*hasher, p.ExternalCalls());
    HashStrings(*hasher, resolved_libs);
    HashStrings(*hasher, p.Parents());
    HashStrings(*hasher, p.Dependencies());
    HashStrings(*hasher, p.UnresolvedDependencies());
    return hasher->Hex();
}

std::string SummaryHashCalculator::ComputeMemoryHash(const std::vector<MemorySegment>& segments) const {
    auto hasher = make_hash();
    hasher->Reset();
    for (const auto& seg : segments) {
        hasher->AddString(seg.Name());
        hasher->AddUint64(seg.Address());
        hasher->AddString(hash_service_.HashBytes(seg.Bytes()));
    }
    return hasher->Hex();
}

std::string SummaryHashCalculator::ComputeSummaryHash(
    const std::string& binary_hash, const std::string& memory_hash, bool can_split,
    const std::vector<std::string>& required_libraries,
    const std::vector<LibraryInfo>& libraries,
    const std::vector<std::pair<std::string, std::string>>& partition_hashes,
    const std::string& binary_os,
    const std::string& binary_format) const {
    auto hasher = make_hash();
    hasher->Reset();
    if (!binary_os.empty())
        hasher->AddString(binary_os);
    if (!binary_format.empty())
        hasher->AddString(binary_format);
    hasher->AddString(binary_hash);
    hasher->AddString(memory_hash);
    hasher->AddBool(can_split);

    auto libs_sorted = required_libraries;
    std::sort(libs_sorted.begin(), libs_sorted.end());
    HashStrings(*hasher, libs_sorted);

    std::vector<LibraryInfo> libs = libraries;
    std::sort(libs.begin(), libs.end(), [](const auto& a, const auto& b) { return a.Name() < b.Name(); });
    for (const auto& lib : libs) {
        hasher->AddString(lib.Name());
        hasher->AddString(lib.Path());
        hasher->AddString(lib.Soname().empty() ? lib.Name() : lib.Soname());
        hasher->AddString(lib.BuildId());
    }

    std::vector<std::pair<std::string, std::string>> parts = partition_hashes;
    std::sort(parts.begin(), parts.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    for (const auto& ph : parts) {
        hasher->AddString(ph.first);   // id
        hasher->AddString(ph.second);  // hash
    }

    return hasher->Hex();
}

std::string SummaryHashCalculator::AlgorithmName() const {
    if (algorithm_) {
        if (dynamic_cast<FnvHashAlgorithm*>(algorithm_.get()))
            return "fnv";
        if (dynamic_cast<StdHashAlgorithm*>(algorithm_.get()))
            return "std";
        return "custom";
    }
    return hash_service_.AlgorithmName();
}

}  // namespace splitter
