#pragma once

#include "artifacts/HashAlgorithm.hpp"
#include "support/FnvHasher.hpp"

namespace splitter {

class FnvHashAlgorithm : public IHashAlgorithm {
public:
    FnvHashAlgorithm() = default;

    void Reset() override;
    void AddByte(uint8_t b) override;
    void AddString(std::string_view s) override;
    void AddUint64(uint64_t v) override;
    void AddBool(bool v) override;
    std::string Hex() const override;
    std::unique_ptr<IHashAlgorithm> Clone() const override;

private:
    FnvHasher hasher_;
};

}  // namespace splitter
