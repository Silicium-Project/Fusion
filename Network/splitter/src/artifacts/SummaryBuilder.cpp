#include "artifacts/SummaryBuilder.hpp"

#include <algorithm>
#include <iomanip>
#include <optional>
#include <sstream>

#include "support/StringUtil.hpp"

namespace splitter {

namespace {

constexpr unsigned kSummarySchemaVersion = 1;

std::string HexString(uint64_t value) {
    std::ostringstream oss;
    oss << "0x" << std::hex << value;
    return oss.str();
}

std::string BytesToHex(const std::vector<uint8_t>& bytes) {
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (uint8_t byte : bytes)
        oss << std::setw(2) << static_cast<int>(byte);
    return oss.str();
}

template <typename Range>
std::string ToSortedJsonArray(const Range& values) {
    std::vector<std::string> sorted(values.begin(), values.end());
    std::sort(sorted.begin(), sorted.end());
    return RangeToJson(sorted);
}

std::string SerializeLibraries(const std::vector<LibraryInfo>& libs) {
    std::ostringstream oss;
    oss << "  \"libraries\": [\n";
    for (size_t i = 0; i < libs.size(); ++i) {
        const auto& lib = libs[i];
        oss << "    {\n";
        oss << "      \"name\": \"" << JsonEscape(lib.Name()) << "\",\n";
        oss << "      \"path\": \"" << JsonEscape(lib.Path()) << "\",\n";
        oss << "      \"soname\": \"" << JsonEscape(lib.Soname()) << "\",\n";
        oss << "      \"build_id\": \"" << JsonEscape(lib.BuildId()) << "\"\n";
        oss << "    }";
        if (i + 1 != libs.size())
            oss << ",";
        oss << "\n";
    }
    oss << "  ]";
    return oss.str();
}

std::string SerializePartition(const Partition& partition,
                               const std::optional<PartitionFiles>& files,
                               const std::set<std::string>& required_libs,
                               const std::string& partition_os,
                               const std::string& partition_format) {
    std::ostringstream oss;
    oss << "    {\n";
    oss << "      \"id\": \"" << JsonEscape(partition.Id()) << "\",\n";
    oss << "      \"os\": \"" << JsonEscape(partition_os) << "\",\n";
    oss << "      \"format\": \"" << JsonEscape(partition_format) << "\",\n";
    oss << "      \"start\": \"" << HexString(partition.StartAddr()) << "\",\n";
    oss << "      \"end\": \"" << HexString(partition.EndAddr()) << "\",\n";
    oss << "      \"size\": " << partition.RawBytes().size() << ",\n";
    oss << "      \"parallelizable\": " << (partition.IsParallelizable() ? "true" : "false") << ",\n";
    oss << "      \"requires_display\": " << (partition.RequiresDisplay() ? "true" : "false") << ",\n";
    oss << "      \"inputs\": " << RangeToJson(partition.Inputs()) << ",\n";
    oss << "      \"external_inputs\": " << RangeToJson(partition.ExternalInputs()) << ",\n";
    oss << "      \"outputs\": " << RangeToJson(partition.Outputs()) << ",\n";
    oss << "      \"external_calls\": " << RangeToJson(partition.ExternalCalls()) << ",\n";
    oss << "      \"required_libraries\": " << ToSortedJsonArray(required_libs) << ",\n";
    oss << "      \"parents\": " << VectorToJson(partition.Parents()) << ",\n";
    oss << "      \"dependencies\": " << VectorToJson(partition.Dependencies()) << ",\n";
    oss << "      \"unresolved_calls\": " << VectorToJson(partition.UnresolvedDependencies()) << ",\n";
    oss << "      \"bin_hash\": \"" << JsonEscape(partition.BinHash()) << "\",\n";
    oss << "      \"partition_hash\": \"" << JsonEscape(partition.PartitionHash()) << "\",\n";

    if (files.has_value()) {
        const auto& part_files = *files;
        oss << "      \"asm\": \"" << JsonEscape(part_files.AsmFile()) << "\",\n";
        oss << "      \"bin\": \"" << JsonEscape(part_files.BinFile()) << "\",\n";
        oss << "      \"wrapper\": \"" << JsonEscape(part_files.WrapperFile()) << "\"\n";
    } else {
        oss << "      \"asm\": \"\",\n";
        oss << "      \"bin\": \"\",\n";
        oss << "      \"wrapper\": \"\"\n";
    }

    oss << "    }";
    return oss.str();
}

std::string SerializeMemory(const std::vector<MemorySegment>& segments) {
    std::ostringstream oss;
    oss << "  \"initial_memory\": [\n";
    for (size_t i = 0; i < segments.size(); ++i) {
        const auto& seg = segments[i];
        oss << "    {\n";
        oss << "      \"name\": \"" << JsonEscape(seg.Name()) << "\",\n";
        oss << "      \"address\": \"" << HexString(seg.Address()) << "\",\n";
        oss << "      \"bytes\": \"" << BytesToHex(seg.Bytes()) << "\"\n";
        oss << "    }";
        if (i + 1 != segments.size())
            oss << ",";
        oss << "\n";
    }
    oss << "  ]";
    return oss.str();
}

}  // namespace

void SummaryBuilder::SetBinaryInfo(const std::string& binary_path,
                                   const std::string& binary_os,
                                   const std::string& binary_format,
                                   const std::string& binary_hash,
                                   const std::string& hash_algo,
                                   const std::string& memory_hash,
                                   bool can_split,
                                   const std::string& summary_hash) {
    std::ostringstream oss;
    oss << "{\n";
    oss << "  \"schema_version\": " << kSummarySchemaVersion << ",\n";
    oss << "  \"binary\": \"" << JsonEscape(binary_path) << "\",\n";
    oss << "  \"binary_os\": \"" << JsonEscape(binary_os) << "\",\n";
    oss << "  \"binary_format\": \"" << JsonEscape(binary_format) << "\",\n";
    oss << "  \"binary_hash\": \"" << JsonEscape(binary_hash) << "\",\n";
    oss << "  \"hash_algo\": \"" << JsonEscape(hash_algo) << "\",\n";
    oss << "  \"can_split\": " << (can_split ? "true" : "false") << ",\n";
    oss << "  \"memory_hash\": \"" << JsonEscape(memory_hash) << "\",\n";
    oss << "  \"summary_hash\": \"" << JsonEscape(summary_hash) << "\"\n";
    header_ = oss.str();
}

void SummaryBuilder::SetCounts(std::size_t partition_count, std::size_t parallelizable_count) {
    std::ostringstream oss;
    oss << "  \"partitions_count\": " << partition_count << ",\n";
    oss << "  \"parallelizable_count\": " << parallelizable_count;
    counts_ = oss.str();
}

void SummaryBuilder::SetRequiredLibraries(const std::vector<std::string>& libs) {
    required_libraries_ = "  \"required_libraries\": " + VectorToJson(libs);
}

void SummaryBuilder::SetLibraries(const std::vector<LibraryInfo>& libs) {
    libraries_ = SerializeLibraries(libs);
}

void SummaryBuilder::AddPartition(const Partition& partition,
                                  const std::optional<PartitionFiles>& files,
                                  const std::set<std::string>& required_libraries,
                                  const std::string& partition_os,
                                  const std::string& partition_format) {
    if (!partitions_.empty())
        partitions_ += ",\n";
    partitions_ += SerializePartition(partition, files, required_libraries, partition_os, partition_format);
}

void SummaryBuilder::SetPartitionHashes(const std::vector<std::pair<std::string, std::string>>& hashes) {
    std::ostringstream oss;
    oss << "  \"partition_hashes\": [\n";
    for (size_t i = 0; i < hashes.size(); ++i) {
        const auto& ph = hashes[i];
        oss << "    {\"id\": \"" << JsonEscape(ph.first) << "\", \"hash\": \"" << JsonEscape(ph.second)
            << "\"}";
        if (i + 1 != hashes.size())
            oss << ",";
        oss << "\n";
    }
    oss << "  ]";
    partition_hashes_ = oss.str();
}

void SummaryBuilder::SetMemorySegments(const std::vector<MemorySegment>& segments) {
    memory_ = SerializeMemory(segments);
}

std::string SummaryBuilder::Build() const {
    std::ostringstream oss;
    oss << header_ << ",\n";
    if (!counts_.empty())
        oss << counts_ << ",\n";
    if (!required_libraries_.empty())
        oss << required_libraries_ << ",\n";
    if (!libraries_.empty())
        oss << libraries_ << ",\n";
    oss << "  \"partitions\": [\n" << partitions_ << "\n  ],\n";
    oss << partition_hashes_;
    if (!memory_.empty())
        oss << ",\n" << memory_ << "\n";
    else
        oss << "\n";
    oss << "}\n";
    return oss.str();
}

}  // namespace splitter
