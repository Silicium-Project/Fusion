#pragma once

#include <string>

namespace splitter {

class PartitionFiles {
public:
    const std::string& AsmFile() const noexcept { return asm_file_; }
    void SetAsmFile(std::string path) noexcept { asm_file_ = std::move(path); }

    const std::string& BinFile() const noexcept { return bin_file_; }
    void SetBinFile(std::string path) noexcept { bin_file_ = std::move(path); }

    const std::string& WrapperFile() const noexcept { return wrapper_file_; }
    void SetWrapperFile(std::string path) noexcept { wrapper_file_ = std::move(path); }

private:
    std::string asm_file_;
    std::string bin_file_;
    std::string wrapper_file_;
};

}  // namespace splitter
