#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace splitter {

class MemorySegment {
public:
    const std::string& Name() const noexcept;
    void SetName(std::string name) noexcept;

    uint64_t Address() const noexcept;
    void SetAddress(uint64_t addr) noexcept;

    const std::vector<uint8_t>& Bytes() const noexcept;
    std::vector<uint8_t>& Bytes() noexcept;

private:
    std::string name_;
    uint64_t address_ = 0;
    std::vector<uint8_t> bytes_;
};

}  // namespace splitter
