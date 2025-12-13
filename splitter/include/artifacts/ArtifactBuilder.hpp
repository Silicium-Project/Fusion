#pragma once

#include <string>

#include "core/Partition.hpp"
#include "core/PartitionFiles.hpp"

namespace splitter {

class ArtifactBuilder {
public:
    explicit ArtifactBuilder(std::string output_dir);

    PartitionFiles CreatePartition(const Partition& partition) const;

    [[nodiscard]] const std::string& OutputDir() const noexcept;

private:
    void WriteTextFile(const std::string& path, const std::string& content) const;
    void WriteBinaryFile(const std::string& path, const std::vector<uint8_t>& data) const;
    void WriteWrapper(const std::string& path, const std::string& partition_id) const;

    std::string output_dir_;
};

}  // namespace splitter
