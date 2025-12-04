#include "fragment/hash.hpp"

#include <sstream>
#include <iomanip>

namespace fragment {

Fnv1aHasher::Fnv1aHasher() : state_(0xcbf29ce484222325ULL) {}

void Fnv1aHasher::reset() { state_ = 0xcbf29ce484222325ULL; }

void Fnv1aHasher::add_byte(uint8_t b) {
    state_ ^= static_cast<uint64_t>(b);
    state_ *= 0x100000001b3ULL;
}

void Fnv1aHasher::add_string(std::string_view s) {
    for (unsigned char c : s)
        add_byte(c);
    add_byte(0xff);
}

void Fnv1aHasher::add_uint64(uint64_t v) {
    for (int i = 0; i < 8; ++i)
        add_byte(static_cast<uint8_t>((v >> (i * 8)) & 0xff));
    add_byte(0xfe);
}

void Fnv1aHasher::add_bool(bool v) {
    add_byte(v ? 0x01 : 0x00);
    add_byte(0xfd);
}

std::string Fnv1aHasher::hex() const {
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << state_;
    return oss.str();
}

}  // namespace fragment
