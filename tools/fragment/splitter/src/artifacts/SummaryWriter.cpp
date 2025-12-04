#include "splitter/artifacts/SummaryWriter.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <set>
#include <sstream>
#include <unordered_map>

#include "splitter/artifacts/SummaryHashCalculator.hpp"
#include "splitter/support/HashUtil.hpp"
#include "splitter/support/StringUtil.hpp"
#include "splitter/support/FlatMap.hpp"
#include "splitter/support/Env.hpp"

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

std::string HexString(uint64_t value) {
    std::ostringstream oss;
    oss << "0x" << std::hex << value;
    return oss.str();
}

std::optional<std::reference_wrapper<const PartitionFiles>> ArtifactFor(
    size_t idx, const std::vector<PartitionFiles>& artifacts) {
    if (idx >= artifacts.size())
        return std::nullopt;
    return std::cref(artifacts[idx]);
}

void WritePartitionEntry(std::ofstream& out,
                         const Partition& partition,
                         const std::optional<std::reference_wrapper<const PartitionFiles>>& files,
                         const FlatStringMap& symbol_index,
                         bool is_last) {
    out << "    {\n";
    out << "      \"id\": \"" << JsonEscape(partition.Id()) << "\",\n";
    out << "      \"start\": \"" << HexString(partition.StartAddr()) << "\",\n";
    out << "      \"end\": \"" << HexString(partition.EndAddr()) << "\",\n";
    out << "      \"size\": " << partition.RawBytes().size() << ",\n";
    out << "      \"parallelizable\": " << (partition.IsParallelizable() ? "true" : "false") << ",\n";
    out << "      \"inputs\": " << RangeToJson(partition.Inputs()) << ",\n";
    out << "      \"external_inputs\": " << RangeToJson(partition.ExternalInputs()) << ",\n";
    out << "      \"external_calls\": " << RangeToJson(partition.ExternalCalls()) << ",\n";
    out << "      \"requires_display\": " << (partition.RequiresDisplay() ? "true" : "false") << ",\n";
    out << "      \"bin_hash\": \"" << JsonEscape(partition.BinHash()) << "\",\n";
    out << "      \"outputs\": " << RangeToJson(partition.Outputs()) << ",\n";
    out << "      \"parents\": " << VectorToJson(partition.Parents()) << ",\n";
    out << "      \"dependencies\": " << VectorToJson(partition.Dependencies()) << ",\n";
    out << "      \"unresolved_calls\": " << VectorToJson(partition.UnresolvedDependencies()) << ",\n";
    out << "      \"required_libraries\": "
                << RangeToJson(ResolvePartitionLibraries(partition, symbol_index)) << ",\n";
    out << "      \"partition_hash\": \"" << JsonEscape(partition.PartitionHash()) << "\",\n";

    if (files.has_value()) {
        const auto& part_files = files->get();
        out << "      \"asm\": \"" << JsonEscape(part_files.AsmFile()) << "\",\n";
        out << "      \"bin\": \"" << JsonEscape(part_files.BinFile()) << "\",\n";
        out << "      \"wrapper\": \"" << JsonEscape(part_files.WrapperFile()) << "\"\n";
    } else {
        out << "      \"asm\": \"\",\n";
        out << "      \"bin\": \"\",\n";
        out << "      \"wrapper\": \"\"\n";
    }

    out << "    }";
    if (!is_last)
        out << ",";
    out << "\n";
}

static std::string BytesToHex(const std::vector<uint8_t>& bytes) {
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (uint8_t byte : bytes)
        oss << std::setw(2) << static_cast<int>(byte);
    return oss.str();
}

}  // namespace

SummaryWriter::SummaryWriter(std::string output_dir,
                             std::shared_ptr<const ILibraryScanner> scanner,
                             std::shared_ptr<const SummaryHashCalculator> hash_calculator)
    : output_dir_(std::move(output_dir)),
      scanner_(std::move(scanner)),
      hash_calculator_(hash_calculator ? std::move(hash_calculator)
                                       : std::make_shared<SummaryHashCalculator>()) {
    fs::create_directories(output_dir_);
}

SummaryWriter::SummaryWriter(std::string output_dir,
                             std::shared_ptr<const ILibraryScanner> scanner,
                             HashService hash_service)
    : SummaryWriter(std::move(output_dir), std::move(scanner),
                    std::make_shared<SummaryHashCalculator>(nullptr, std::move(hash_service))) {}

void SummaryWriter::Write(const std::vector<Partition>& partitions,
                          const std::vector<PartitionFiles>& artifacts,
                          const std::vector<MemorySegment>& memory_segments,
                          const std::string& binary_path) const {
    fs::create_directories(output_dir_);

    std::string summary_path = output_dir_ + "/summary.json";
    std::ofstream summary;
    if (!OpenSummaryFile(summary_path, summary))
        return;

    auto libraries = scanner_->DetectLibraries(binary_path);
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
    const std::string binary_hash = HashFile(binary_path);
    bool can_split = true;
    if (auto env = GetEnv("SPLITTER_CAN_SPLIT"))
        can_split = *env != "0" && *env != "false";

    std::vector<Partition> partitions_copy = partitions;
    std::vector<std::pair<std::string, std::string>> partition_hashes;
    partition_hashes.reserve(partitions_copy.size());
    for (auto& p : partitions_copy) {
        auto resolved_libs = ResolvePartitionLibraries(p, symbol_index);
        p.SetPartitionHash(hash_calculator_->ComputePartitionHash(p, resolved_libs));
        partition_hashes.emplace_back(p.Id(), p.PartitionHash());
    }

    const std::string memory_hash = hash_calculator_->ComputeMemoryHash(memory_segments);
    const std::string summary_hash =
        hash_calculator_->ComputeSummaryHash(binary_hash, memory_hash, can_split, library_names, libraries,
                                             partition_hashes);

    WriteHeader(summary, binary_path, partitions_copy.size(), CountParallelizable(partitions_copy),
                library_names, libraries, binary_hash, can_split, memory_hash, summary_hash);
    WritePartitions(summary, partitions_copy, artifacts, symbol_index);
    summary << "  ],\n";
    WriteMemory(summary, memory_segments);
    WriteFooter(summary);

    std::cout << "\nRésumé: " << summary_path << "\n";
}

bool SummaryWriter::OpenSummaryFile(const std::string& path, std::ofstream& out) const {
    out.open(path);
    if (out)
        return true;
    std::cerr << "Avertissement: impossible d'écrire " << path << "\n";
    return false;
}

void SummaryWriter::WriteHeader(std::ofstream& out,
                                const std::string& binary_path,
                                size_t partition_count,
                                size_t parallelizable_count,
                                const std::vector<std::string>& required_libraries,
                                const std::vector<LibraryInfo>& libraries,
                                const std::string& binary_hash,
                                bool can_split,
                                const std::string& memory_hash,
                                const std::string& summary_hash) const {
    out << "{\n";
    out << "  \"binary\": \"" << JsonEscape(binary_path) << "\",\n";
    out << "  \"binary_hash\": \"" << JsonEscape(binary_hash) << "\",\n";
    out << "  \"can_split\": " << (can_split ? "true" : "false") << ",\n";
    out << "  \"memory_hash\": \"" << JsonEscape(memory_hash) << "\",\n";
    out << "  \"summary_hash\": \"" << JsonEscape(summary_hash) << "\",\n";
    out << "  \"partitions_count\": " << partition_count << ",\n";
    out << "  \"parallelizable_count\": " << parallelizable_count << ",\n";
    out << "  \"required_libraries\": " << VectorToJson(required_libraries) << ",\n";
    out << "  \"libraries\": [\n";
    for (size_t i = 0; i < libraries.size(); ++i) {
        const auto& lib = libraries[i];
        const bool is_last = (i + 1 == libraries.size());
        out << "    {\n";
        out << "      \"name\": \"" << JsonEscape(lib.Name()) << "\",\n";
        out << "      \"path\": \"" << JsonEscape(lib.Path()) << "\",\n";
        out << "      \"soname\": \"" << JsonEscape(lib.Soname().empty() ? lib.Name() : lib.Soname()) << "\",\n";
        out << "      \"build_id\": \"" << JsonEscape(lib.BuildId()) << "\"\n";
        out << "    }" << (is_last ? "" : ",") << "\n";
    }
    out << "  ],\n";
    out << "  \"partitions\": [\n";
}

void SummaryWriter::WriteFooter(std::ofstream& out) const {
    out << "}\n";
}

void SummaryWriter::WritePartitions(std::ofstream& out,
                                    const std::vector<Partition>& partitions,
                                    const std::vector<PartitionFiles>& artifacts,
                                    const FlatStringMap& symbol_index) const {
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        const bool is_last = (idx + 1 == partitions.size());
        WritePartitionEntry(out, partitions[idx], ArtifactFor(idx, artifacts), symbol_index, is_last);
    }
}

void SummaryWriter::WriteMemory(std::ofstream& out, const std::vector<MemorySegment>& memory_segments) const {
    out << "  \"initial_memory\": [\n";
    for (size_t idx = 0; idx < memory_segments.size(); ++idx) {
        const auto& segment = memory_segments[idx];
        bool is_last = (idx + 1 == memory_segments.size());
        out << "    {\n";
        out << "      \"name\": \"" << JsonEscape(segment.Name()) << "\",\n";
        out << "      \"address\": \"0x" << std::hex << segment.Address() << "\",\n";
        out << std::dec;
        out << "      \"bytes\": \"" << BytesToHex(segment.Bytes()) << "\"\n";
        out << "    }" << (is_last ? "\n" : ",\n");
    }
    out << "  ]\n";
}

}  // namespace splitter
