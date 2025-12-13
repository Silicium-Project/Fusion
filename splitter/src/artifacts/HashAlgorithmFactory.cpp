#include "artifacts/HashAlgorithmFactory.hpp"

#include "artifacts/FnvHashAlgorithm.hpp"
#include "artifacts/StdHashAlgorithm.hpp"

namespace splitter {

std::shared_ptr<IHashAlgorithm> HashAlgorithmFactory::Create(const std::string& name) {
    if (name == "std")
        return std::make_shared<StdHashAlgorithm>();
    return std::make_shared<FnvHashAlgorithm>();
}

}  // namespace splitter
