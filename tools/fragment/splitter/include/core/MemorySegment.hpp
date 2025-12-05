#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace splitter {

class MemorySegment {
public:
    const std::string& Name() const noexcept { return name_; }
    void SetName(std::string name) noexcept { name_ = std::move(name); }

    uint64_t Address() const noexcept { return address_; }
    void SetAddress(uint64_t addr) noexcept { address_ = addr; }

    const std::vector<uint8_t>& Bytes() const noexcept { return bytes_; }
    std::vector<uint8_t>& Bytes() noexcept { return bytes_; }

private:
    std::string name_;
    uint64_t address_ = 0;
    std::vector<uint8_t> bytes_;
};

}  // namespace splitter
