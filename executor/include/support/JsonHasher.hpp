#pragma once

#include <jansson.h>

#include <memory>
#include <string>

#include "support/Hash.hpp"

namespace fragment {

// Hachage canonique d'arbres JSON (jansson) avec tri des clés pour
// assurer la stabilité quel que soit l'ordre d'écriture.
class JsonHasher {
public:
    explicit JsonHasher(std::unique_ptr<Hasher> algo = nullptr);

    // Intègre une valeur JSON (objet, tableau, scalaire).
    void add(json_t* value);

    // Retourne le hash hexadécimal.
    std::string hex() const;

private:
    std::unique_ptr<Hasher> hasher_;

    void hash_value(json_t* value);
    void hash_object(json_t* obj);
    void hash_array(json_t* arr);
};

}  // namespace fragment
