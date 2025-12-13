#include "core/PartitionFiles.hpp"

namespace splitter {

const std::string& PartitionFiles::AsmFile() const noexcept {
    return asm_file_;
}

void PartitionFiles::SetAsmFile(std::string path) noexcept {
    asm_file_ = std::move(path);
}

const std::string& PartitionFiles::BinFile() const noexcept {
    return bin_file_;
}

void PartitionFiles::SetBinFile(std::string path) noexcept {
    bin_file_ = std::move(path);
}

const std::string& PartitionFiles::WrapperFile() const noexcept {
    return wrapper_file_;
}

void PartitionFiles::SetWrapperFile(std::string path) noexcept {
    wrapper_file_ = std::move(path);
}

}  // namespace splitter
