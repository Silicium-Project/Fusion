#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>

namespace fragment {

// Interface générique pour un algorithme de hachage.
class Hasher {
    public:
        virtual ~Hasher() = default;
        virtual void reset() = 0;
        virtual void add_byte(uint8_t b) = 0;
        virtual void add_string(std::string_view s) = 0;
        virtual void add_uint64(uint64_t v) = 0;
        virtual void add_bool(bool v) = 0;
        virtual std::string hex() const = 0;
};

// Implémentation FNV-1a 64-bit (par défaut).
class Fnv1aHasher : public Hasher {
    public:
        Fnv1aHasher();
        void reset() override;
        void add_byte(uint8_t b) override;
        void add_string(std::string_view s) override;
        void add_uint64(uint64_t v) override;
        void add_bool(bool v) override;
        std::string hex() const override;

    private:
        uint64_t state_;
};

// Implémentation "std" alignée sur le splitter.
class StdHasher : public Hasher {
    public:
        StdHasher();
        void reset() override;
        void add_byte(uint8_t b) override;
        void add_string(std::string_view s) override;
        void add_uint64(uint64_t v) override;
        void add_bool(bool v) override;
        std::string hex() const override;

    private:
        uint64_t state_;
        void mix(uint64_t value);
};

// Alias pour compatibilité et usage par défaut.
using DefaultHasher = Fnv1aHasher;
using FnvHasher = Fnv1aHasher;

// Décorateur de séparation de domaine : préfixe tous les hachages par un
// identifiant logique (partition/memory/summary, etc.).
class DomainHasher : public Hasher {
public:
    explicit DomainHasher(std::string_view domain, std::unique_ptr<Hasher> algo = nullptr);

    void reset() override;
    void add_byte(uint8_t b) override;
    void add_string(std::string_view s) override;
    void add_uint64(uint64_t v) override;
    void add_bool(bool v) override;
    std::string hex() const override;

private:
    std::string domain_;
    std::unique_ptr<Hasher> algo_;

    void prefix();
};

}  // namespace fragment
