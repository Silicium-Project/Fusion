#pragma once

#include "artifacts/HashAlgorithm.hpp"
#include "support/FnvHasher.hpp"

namespace splitter {

class FnvHashAlgorithm : public IHashAlgorithm {
public:
    FnvHashAlgorithm() = default;

    void Reset() override { hasher_ = FnvHasher(); }
    void AddByte(uint8_t b) override { hasher_.AddByte(b); }
    void AddString(std::string_view s) override { hasher_.AddString(s); }
    void AddUint64(uint64_t v) override { hasher_.AddUint64(v); }
    void AddBool(bool v) override { hasher_.AddBool(v); }
    std::string Hex() const override { return hasher_.Hex(); }
    std::unique_ptr<IHashAlgorithm> Clone() const override {
        return std::make_unique<FnvHashAlgorithm>();
    }

private:
    FnvHasher hasher_;
};

}  // namespace splitter
