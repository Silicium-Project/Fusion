#include "support/FnvHasher.hpp"

#include <iomanip>
#include <sstream>

namespace splitter {

FnvHasher::FnvHasher() : state_(0xcbf29ce484222325ULL) {}

void FnvHasher::AddByte(uint8_t b) {
    state_ ^= static_cast<uint64_t>(b);
    state_ *= 0x100000001b3ULL;
}

void FnvHasher::AddString(std::string_view s) {
    for (unsigned char c : s)
        AddByte(c);
    AddByte(0xff);  // séparateur
}

void FnvHasher::AddUint64(uint64_t v) {
    for (int i = 0; i < 8; ++i)
        AddByte(static_cast<uint8_t>((v >> (i * 8)) & 0xff));
    AddByte(0xfe);
}

void FnvHasher::AddBool(bool v) {
    AddByte(v ? 0x01 : 0x00);
    AddByte(0xfd);
}

std::string FnvHasher::Hex() const {
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << state_;
    return oss.str();
}

}  // namespace splitter
