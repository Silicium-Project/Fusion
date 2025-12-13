#include "support/HashService.hpp"

#include <fstream>

#include "support/Env.hpp"

namespace splitter {

HashService::HashService()
: HashService(std::make_shared<FnvHashAlgorithm>()) {}

HashService::HashService(std::shared_ptr<IHashAlgorithm> prototype)
: prototype_(std::move(prototype)) {}

void HashService::SetAlgorithm(std::shared_ptr<IHashAlgorithm> prototype) {
    prototype_ = std::move(prototype);
}

std::unique_ptr<IHashAlgorithm> HashService::MakeHasher() const {
    if (prototype_)
        return prototype_->Clone();
    return std::make_unique<FnvHashAlgorithm>();
}

std::string HashService::HashBytes(const std::vector<uint8_t>& data) const {
    auto hasher = MakeHasher();
    hasher->Reset();
    for (uint8_t byte : data)
        hasher->AddByte(byte);
    return hasher->Hex();
}

std::string HashService::HashString(std::string_view data) const {
    auto hasher = MakeHasher();
    hasher->Reset();
    if (!data.empty())
        hasher->AddString(data);
    return hasher->Hex();
}

std::string HashService::HashFile(const std::string& path) const {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open())
        return {};
    std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());
    return HashBytes(buffer);
}

HashService MakeHashServiceFromEnv() {
    auto algo = GetEnv("SPLITTER_HASH_ALGO");
    if (!algo)
        return HashService(std::make_shared<FnvHashAlgorithm>());
    std::string name(*algo);
    if (name == "std")
        return HashService(std::make_shared<StdHashAlgorithm>());
    return HashService(std::make_shared<FnvHashAlgorithm>());
}

}  // namespace splitter
