#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>

#include "partition/PartitionSummary.hpp"

namespace {

std::filesystem::path write_summary_file(const std::optional<uint32_t>& schema_version) {
    const auto path = std::filesystem::temp_directory_path() / "worker_summary_schema_test.json";

    std::ostringstream summary;
    summary << "{\n";
    if (schema_version.has_value())
        summary << "  \"schema_version\": " << *schema_version << ",\n";
    summary << "  \"binary\":\"/tmp/dummy.bin\",\n";
    summary << "  \"binary_os\":\"linux\",\n";
    summary << "  \"binary_format\":\"elf\",\n";
    summary << "  \"binary_hash\":\"\",\n";
    summary << "  \"hash_algo\":\"fnv\",\n";
    summary << "  \"can_split\":true,\n";
    summary << "  \"memory_hash\":\"\",\n";
    summary << "  \"summary_hash\":\"\",\n";
    summary << "  \"required_libraries\":[],\n";
    summary << "  \"libraries\":[],\n";
    summary << "  \"partitions\":[{\n";
    summary << "    \"id\":\"p0\",\n";
    summary << "    \"os\":\"linux\",\n";
    summary << "    \"format\":\"elf\",\n";
    summary << "    \"start\":\"0x0\",\n";
    summary << "    \"end\":\"0x0\",\n";
    summary << "    \"size\":0,\n";
    summary << "    \"parallelizable\":true,\n";
    summary << "    \"requires_display\":false,\n";
    summary << "    \"inputs\":[],\n";
    summary << "    \"external_inputs\":[],\n";
    summary << "    \"outputs\":[],\n";
    summary << "    \"external_calls\":[],\n";
    summary << "    \"required_libraries\":[],\n";
    summary << "    \"parents\":[],\n";
    summary << "    \"dependencies\":[],\n";
    summary << "    \"unresolved_calls\":[],\n";
    summary << "    \"bin_hash\":\"\",\n";
    summary << "    \"partition_hash\":\"\",\n";
    summary << "    \"asm\":\"p0.asm\",\n";
    summary << "    \"bin\":\"\",\n";
    summary << "    \"wrapper\":\"\"\n";
    summary << "  }],\n";
    summary << "  \"partition_hashes\":[]\n";
    summary << "}\n";

    std::ofstream out(path);
    out << summary.str();
    out.close();
    return path;
}

TEST(PartitionSummarySchema, AcceptsCurrentVersion) {
    const auto path = write_summary_file(1);
    const auto summary = fragment::load_partition_summary(path.string(), true);
    EXPECT_EQ(fragment::kPartitionSummarySchemaVersion, summary.schema_version);
    ASSERT_EQ(1u, summary.partitions.size());
}

TEST(PartitionSummarySchema, AcceptsLegacyWithoutVersion) {
    const auto path = write_summary_file(std::nullopt);
    const auto summary = fragment::load_partition_summary(path.string(), true);
    EXPECT_EQ(fragment::kPartitionSummarySchemaVersion, summary.schema_version);
    ASSERT_EQ(1u, summary.partitions.size());
}

TEST(PartitionSummarySchema, RejectsUnsupportedVersion) {
    const auto path = write_summary_file(99);
    EXPECT_THROW(fragment::load_partition_summary(path.string(), true), std::runtime_error);
}

}  // namespace
