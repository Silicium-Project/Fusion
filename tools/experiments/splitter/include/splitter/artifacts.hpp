#pragma once

#include <cstddef>
#include <fstream>
#include <string>
#include <vector>

#include "splitter/types.hpp"

namespace splitter {

    class ArtifactBuilder {
    public:
        explicit ArtifactBuilder(std::string output_dir);

        PartitionFiles create_partition(const BinaryPartition& partition) const;
        void write_summary(const std::vector<BinaryPartition>& partitions,
                           const std::vector<PartitionFiles>& artifacts,
                           const std::vector<MemorySegment>& memory_segments,
                           const std::string& binary_path) const;

        [[nodiscard]] const std::string& output_dir() const noexcept {
            return output_dir_;
        }

    private:
        void write_text_file(const std::string& path, const std::string& content) const;
        void write_binary_file(const std::string& path, const std::vector<uint8_t>& data) const;
        void write_wrapper(const std::string& path, const std::string& partition_id) const;
        bool open_summary_file(const std::string& path, std::ofstream& out) const;
        void write_summary_header(std::ofstream& out,
                                  const std::string& binary_path,
                                  size_t partition_count,
                                  size_t parallelizable_count) const;
        void write_summary_footer(std::ofstream& out) const;
        void write_partitions_block(std::ofstream& out,
                                    const std::vector<BinaryPartition>& partitions,
                                    const std::vector<PartitionFiles>& artifacts) const;
        void write_memory_block(std::ofstream& out,
                                const std::vector<MemorySegment>& memory_segments) const;

        std::string output_dir_;
    };

    PartitionFiles create_standalone_partition(
        const BinaryPartition& partition, const std::string& output_dir);

    void write_summary(const std::vector<BinaryPartition>& partitions,
                       const std::vector<PartitionFiles>& artifacts,
                       const std::vector<MemorySegment>& memory_segments,
                       const std::string& output_dir,
                       const std::string& binary_path);

}  // namespace splitter
