#pragma once

#include <string>

namespace splitter {

class PartitionFiles {
public:
    const std::string& AsmFile() const noexcept;
    void SetAsmFile(std::string path) noexcept;

    const std::string& BinFile() const noexcept;
    void SetBinFile(std::string path) noexcept;

    const std::string& WrapperFile() const noexcept;
    void SetWrapperFile(std::string path) noexcept;

private:
    std::string asm_file_;
    std::string bin_file_;
    std::string wrapper_file_;
};

}  // namespace splitter
