#include "artifacts/SummaryWriter.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <set>
#include <sstream>
#include <unordered_map>

#include "artifacts/SummaryHashCalculator.hpp"
#include "support/HashUtil.hpp"
#include "support/StringUtil.hpp"
#include "support/FlatMap.hpp"
#include "support/Env.hpp"
#include "artifacts/SummaryBuilder.hpp"

namespace splitter {

namespace fs = std::filesystem;

namespace {

size_t CountParallelizable(const std::vector<Partition>& partitions) {
    size_t count = 0;
    for (const auto& partition : partitions)
        if (partition.IsParallelizable())
            ++count;
    return count;
}

std::set<std::string> ResolvePartitionLibraries(const Partition& partition, const FlatStringMap& symbol_index) {
    std::set<std::string> names;
    for (const auto& symbol : partition.ExternalCalls()) {
        auto it = symbol_index.find(symbol);
        if (it != symbol_index.end())
            names.insert(it->second);
    }
    return names;
}

}  // namespace

SummaryWriter::SummaryWriter(std::filesystem::path output_dir,
                             std::shared_ptr<const ILibraryScanner> scanner,
                             std::shared_ptr<const SummaryHashCalculator> hash_calculator)
    : output_dir_(std::move(output_dir)),
      scanner_(std::move(scanner)),
      hash_calculator_(hash_calculator ? std::move(hash_calculator)
                                       : std::make_shared<SummaryHashCalculator>()) {
    fs::create_directories(output_dir_);
}

SummaryWriter::SummaryWriter(std::filesystem::path output_dir,
                             std::shared_ptr<const ILibraryScanner> scanner,
                             HashService hash_service)
    : SummaryWriter(std::move(output_dir), std::move(scanner),
                    std::make_shared<SummaryHashCalculator>(nullptr, std::move(hash_service))) {}

void SummaryWriter::Write(const std::vector<Partition>& partitions,
                          const std::vector<PartitionFiles>& artifacts,
                          const std::vector<MemorySegment>& memory_segments,
                          const std::filesystem::path& binary_path) const {
    fs::create_directories(output_dir_);

    const std::string abs_binary = fs::absolute(binary_path).string();
    auto libraries = scanner_->DetectLibraries(abs_binary);
    std::vector<std::string> library_names;
    {
        std::set<std::string> unique;
        for (const auto& entry : libraries)
            unique.insert(entry.Name());
        library_names.assign(unique.begin(), unique.end());
    }
    FlatStringMap symbol_index;
    for (const auto& kv : scanner_->BuildSymbolIndex(libraries))
        symbol_index.insert(kv.first, kv.second);
    const std::string binary_hash = HashFile(abs_binary);
    bool can_split = true;
    if (auto env = GetEnv("SPLITTER_CAN_SPLIT"))
        can_split = *env != "0" && *env != "false";

    std::vector<Partition> partitions_copy = partitions;
    std::vector<std::pair<std::string, std::string>> partition_hashes;
    partition_hashes.clear();
    for (auto& p : partitions_copy) {
        auto resolved_libs = ResolvePartitionLibraries(p, symbol_index);
        p.SetPartitionHash(hash_calculator_->ComputePartitionHash(p, resolved_libs));
        partition_hashes.emplace_back(p.Id(), p.PartitionHash());
    }

    const std::string memory_hash = hash_calculator_->ComputeMemoryHash(memory_segments);
    const std::string summary_hash =
        hash_calculator_->ComputeSummaryHash(binary_hash, memory_hash, can_split, library_names, libraries,
                                             partition_hashes);

    SummaryBuilder builder;
    builder.SetBinaryInfo(abs_binary, binary_hash, memory_hash, can_split, summary_hash);
    builder.SetCounts(partitions_copy.size(), CountParallelizable(partitions_copy));
    builder.SetRequiredLibraries(library_names);
    builder.SetLibraries(libraries);
    for (size_t idx = 0; idx < partitions_copy.size(); ++idx) {
        std::optional<PartitionFiles> files_opt;
        if (idx < artifacts.size())
            files_opt = artifacts[idx];
        auto req = ResolvePartitionLibraries(partitions_copy[idx], symbol_index);
        builder.AddPartition(partitions_copy[idx], files_opt, req);
    }
    builder.SetPartitionHashes(partition_hashes);
    builder.SetMemorySegments(memory_segments);

    const fs::path summary_path = output_dir_ / "summary.json";
    std::ofstream summary;
    if (!OpenSummaryFile(summary_path, summary))
        return;
    summary << builder.Build();

    std::cout << "\nRésumé: " << summary_path.string() << "\n";
}

bool SummaryWriter::OpenSummaryFile(const std::filesystem::path& path, std::ofstream& out) const {
    out.open(path);
    if (out)
        return true;
    std::cerr << "Avertissement: impossible d'écrire " << path << "\n";
    return false;
}

}  // namespace splitter
