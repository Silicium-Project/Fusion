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

// Alias pour compatibilité et usage par défaut.
using DefaultHasher = Fnv1aHasher;
using FnvHasher = Fnv1aHasher;

// Décorateur de séparation de domaine : préfixe tous les hachages par un
// identifiant logique (partition/memory/summary, etc.).
template <typename Algo = DefaultHasher>
class DomainHasher : public Hasher {
    public:
        explicit DomainHasher(std::string_view domain, Algo algo = Algo())
            : domain_(domain), algo_(std::move(algo)) {
            algo_.reset();
            algo_.add_string(domain_);
            algo_.add_byte(0xa5);
        }

        void reset() override {
            algo_.reset();
            algo_.add_string(domain_);
            algo_.add_byte(0xa5);
        }

        void add_byte(uint8_t b) override { algo_.add_byte(b); }
        void add_string(std::string_view s) override { algo_.add_string(s); }
        void add_uint64(uint64_t v) override { algo_.add_uint64(v); }
        void add_bool(bool v) override { algo_.add_bool(v); }
        std::string hex() const override { return algo_.hex(); }

    private:
        std::string domain_;
        Algo algo_;
    };

}  // namespace fragment
