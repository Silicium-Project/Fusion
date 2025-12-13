#pragma once

#include <memory>
#include <string>

#include "artifacts/HashAlgorithm.hpp"

namespace splitter {

class HashAlgorithmFactory {
public:
    // name: "fnv" (défaut) ou "std".
    static std::shared_ptr<IHashAlgorithm> Create(const std::string& name);
};

}  // namespace splitter
