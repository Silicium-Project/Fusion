#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "artifacts/HashAlgorithm.hpp"
#include "artifacts/FnvHashAlgorithm.hpp"
#include "artifacts/StdHashAlgorithm.hpp"

namespace splitter {

// Service objet qui centralise la stratégie de hashage (algorithme injecté).
class HashService {
public:
    HashService();
    explicit HashService(std::shared_ptr<IHashAlgorithm> prototype);

    void SetAlgorithm(std::shared_ptr<IHashAlgorithm> prototype);

    std::string AlgorithmName() const;
    std::unique_ptr<IHashAlgorithm> CreateHasher() const;

    std::string HashBytes(const std::vector<uint8_t>& data) const;
    std::string HashString(std::string_view data) const;
    std::string HashFile(const std::string& path) const;

private:
    std::unique_ptr<IHashAlgorithm> MakeHasher() const;

    std::shared_ptr<IHashAlgorithm> prototype_;
    std::string algo_name_;
};

// Fabrique utilitaire pour lire la config depuis l'environnement (SPLITTER_HASH_ALGO).
HashService MakeHashServiceFromEnv();

}  // namespace splitter
