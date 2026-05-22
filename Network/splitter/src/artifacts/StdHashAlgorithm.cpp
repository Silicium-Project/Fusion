#include "artifacts/StdHashAlgorithm.hpp"

#include <cstdint>
#include <iomanip>
#include <sstream>

namespace splitter {

namespace {
constexpr uint64_t kSeed = 0x9e3779b97f4a7c15ULL;
}

StdHashAlgorithm::StdHashAlgorithm() : state_(kSeed) {}

void StdHashAlgorithm::Reset() {
    state_ = kSeed;
}

void StdHashAlgorithm::Mix(uint64_t value) {
    state_ ^= value + kSeed + (state_ << 6) + (state_ >> 2);
    state_ = (state_ << 13) | (state_ >> (64 - 13));
}

void StdHashAlgorithm::AddByte(uint8_t b) {
    Mix(static_cast<uint64_t>(b));
}

void StdHashAlgorithm::AddString(std::string_view s) {
    for (unsigned char c : s)
        AddByte(c);
    AddByte(0xfe);
}

void StdHashAlgorithm::AddUint64(uint64_t v) {
    Mix(v);
    AddByte(0xfd);
}

void StdHashAlgorithm::AddBool(bool v) {
    AddByte(v ? 1 : 0);
    AddByte(0xfc);
}

std::string StdHashAlgorithm::Hex() const {
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << state_;
    return oss.str();
}

std::unique_ptr<IHashAlgorithm> StdHashAlgorithm::Clone() const {
    return std::make_unique<StdHashAlgorithm>();
}

}  // namespace splitter
