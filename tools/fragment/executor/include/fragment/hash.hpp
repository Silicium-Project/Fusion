#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace fragment {

// Hash déterministe (FNV-1a 64-bit) utilisé pour vérifier les summaries.
class FnvHasher {
public:
    FnvHasher();
    void add_byte(uint8_t b);
    void add_string(std::string_view s);
    void add_uint64(uint64_t v);
    void add_bool(bool v);
    std::string hex() const;

private:
    uint64_t state_;
};

}  // namespace fragment
