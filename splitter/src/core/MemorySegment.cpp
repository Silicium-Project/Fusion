#include "core/MemorySegment.hpp"

namespace splitter {

const std::string& MemorySegment::Name() const noexcept {
    return name_;
}

void MemorySegment::SetName(std::string name) noexcept {
    name_ = std::move(name);
}

uint64_t MemorySegment::Address() const noexcept {
    return address_;
}

void MemorySegment::SetAddress(uint64_t addr) noexcept {
    address_ = addr;
}

const std::vector<uint8_t>& MemorySegment::Bytes() const noexcept {
    return bytes_;
}

std::vector<uint8_t>& MemorySegment::Bytes() noexcept {
    return bytes_;
}

}  // namespace splitter
