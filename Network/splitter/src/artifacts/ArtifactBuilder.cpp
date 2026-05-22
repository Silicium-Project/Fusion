#include "artifacts/ArtifactBuilder.hpp"

#include <filesystem>
#include <fstream>

namespace splitter {

namespace fs = std::filesystem;

ArtifactBuilder::ArtifactBuilder(std::string output_dir)
    : output_dir_(std::move(output_dir)) {
    fs::create_directories(output_dir_);
}

PartitionFiles ArtifactBuilder::CreatePartition(const Partition& partition) const {
    fs::create_directories(output_dir_);

    PartitionFiles files;
    files.SetAsmFile(output_dir_ + "/" + partition.Id() + ".asm");
    files.SetBinFile(output_dir_ + "/" + partition.Id() + ".bin");
    files.SetWrapperFile(output_dir_ + "/" + partition.Id() + "_wrapper.c");

    WriteTextFile(files.AsmFile(), partition.AsmCode());
    WriteBinaryFile(files.BinFile(), partition.RawBytes());
    WriteWrapper(files.WrapperFile(), partition.Id());
    return files;
}

const std::string& ArtifactBuilder::OutputDir() const noexcept {
    return output_dir_;
}

void ArtifactBuilder::WriteTextFile(const std::string& path, const std::string& content) const {
    std::ofstream file(path);
    file << content;
}

void ArtifactBuilder::WriteBinaryFile(const std::string& path, const std::vector<uint8_t>& data) const {
    std::ofstream file(path, std::ios::binary);
    std::vector<char> buffer(data.begin(), data.end());
    file.write(buffer.data(), static_cast<std::streamsize>(buffer.size()));
}

void ArtifactBuilder::WriteWrapper(const std::string& path, const std::string& partition_id) const {
    std::ofstream wrapper(path);
    wrapper << "// Wrapper pour partition: " << partition_id << "\n"
            << "#include <stdio.h>\n"
            << "#include <stdint.h>\n\n"
            << "extern void partition_code();\n\n"
            << "int main() {\n"
            << "    printf(\"Exécution partition: " << partition_id << "\\n\");\n"
            << "    // partition_code();\n"
            << "    return 0;\n"
            << "}\n";
}

}  // namespace splitter
