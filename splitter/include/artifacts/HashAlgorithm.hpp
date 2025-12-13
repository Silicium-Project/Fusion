#pragma once

#include <cstdint>
#include <memory>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace splitter {

// Interface générique pour un algorithme de hash.
class IHashAlgorithm {
public:
    virtual ~IHashAlgorithm() = default;
    virtual void Reset() = 0;
    virtual void AddByte(uint8_t b) = 0;
    virtual void AddString(std::string_view s) = 0;
    virtual void AddUint64(uint64_t v) = 0;
    virtual void AddBool(bool v) = 0;
    virtual std::string Hex() const = 0;
    virtual std::unique_ptr<IHashAlgorithm> Clone() const = 0;
};

}  // namespace splitter
