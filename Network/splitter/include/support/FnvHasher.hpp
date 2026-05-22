#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace splitter {

// Hash déterministe léger (FNV-1a 64-bit) pour sérialiser des structures.
class FnvHasher {
public:
    FnvHasher();

    void AddByte(uint8_t b);
    void AddString(std::string_view s);
    void AddUint64(uint64_t v);
    void AddBool(bool v);

    [[nodiscard]] std::string Hex() const;

private:
    uint64_t state_;
};

}  // namespace splitter
