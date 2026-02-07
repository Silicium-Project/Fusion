#include "support/HashService.hpp"

#include <fstream>

#include "support/Env.hpp"

namespace splitter {

namespace {

std::string DetectAlgorithmName(const std::shared_ptr<IHashAlgorithm>& prototype) {
    if (!prototype)
        return "fnv";
    if (dynamic_cast<FnvHashAlgorithm*>(prototype.get()))
        return "fnv";
    if (dynamic_cast<StdHashAlgorithm*>(prototype.get()))
        return "std";
    return "custom";
}

}  // namespace

HashService::HashService()
: HashService(std::make_shared<FnvHashAlgorithm>()) {}

HashService::HashService(std::shared_ptr<IHashAlgorithm> prototype)
: prototype_(std::move(prototype)),
  algo_name_(DetectAlgorithmName(prototype_)) {}

void HashService::SetAlgorithm(std::shared_ptr<IHashAlgorithm> prototype) {
    prototype_ = std::move(prototype);
    algo_name_ = DetectAlgorithmName(prototype_);
}

std::unique_ptr<IHashAlgorithm> HashService::MakeHasher() const {
    if (prototype_)
        return prototype_->Clone();
    return std::make_unique<FnvHashAlgorithm>();
}

std::string HashService::AlgorithmName() const {
    return algo_name_.empty() ? "fnv" : algo_name_;
}

std::unique_ptr<IHashAlgorithm> HashService::CreateHasher() const {
    return MakeHasher();
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
