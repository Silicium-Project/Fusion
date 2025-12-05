#include "splitter/artifacts/HashAlgorithmFactory.hpp"

#include "splitter/artifacts/FnvHashAlgorithm.hpp"
#include "splitter/artifacts/StdHashAlgorithm.hpp"

namespace splitter {

std::shared_ptr<IHashAlgorithm> HashAlgorithmFactory::Create(const std::string& name) {
    if (name == "std")
        return std::make_shared<StdHashAlgorithm>();
    return std::make_shared<FnvHashAlgorithm>();
}

}  // namespace splitter
