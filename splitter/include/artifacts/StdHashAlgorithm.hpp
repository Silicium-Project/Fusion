#pragma once

#include <cstdint>
#include <string>
#include <string_view>

#include "artifacts/HashAlgorithm.hpp"

namespace splitter {

// Alternative simple hash basé sur un mélange multiplicatif (différent de FNV).
class StdHashAlgorithm : public IHashAlgorithm {
public:
    StdHashAlgorithm();

    void Reset() override;
    void AddByte(uint8_t b) override;
    void AddString(std::string_view s) override;
    void AddUint64(uint64_t v) override;
    void AddBool(bool v) override;
    std::string Hex() const override;
    std::unique_ptr<IHashAlgorithm> Clone() const override;

private:
    void Mix(uint64_t value);

    uint64_t state_;
};

}  // namespace splitter
