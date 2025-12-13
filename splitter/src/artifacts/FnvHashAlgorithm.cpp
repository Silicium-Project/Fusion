#include "artifacts/FnvHashAlgorithm.hpp"

namespace splitter {

void FnvHashAlgorithm::Reset() {
    hasher_ = FnvHasher();
}

void FnvHashAlgorithm::AddByte(uint8_t b) {
    hasher_.AddByte(b);
}

void FnvHashAlgorithm::AddString(std::string_view s) {
    hasher_.AddString(s);
}

void FnvHashAlgorithm::AddUint64(uint64_t v) {
    hasher_.AddUint64(v);
}

void FnvHashAlgorithm::AddBool(bool v) {
    hasher_.AddBool(v);
}

std::string FnvHashAlgorithm::Hex() const {
    return hasher_.Hex();
}

std::unique_ptr<IHashAlgorithm> FnvHashAlgorithm::Clone() const {
    return std::make_unique<FnvHashAlgorithm>();
}

}  // namespace splitter
