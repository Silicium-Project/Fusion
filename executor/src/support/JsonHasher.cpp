#include "support/JsonHasher.hpp"

#include <algorithm>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace fragment {

namespace {
std::string real_to_string(double v) {
    std::ostringstream oss;
    oss << std::setprecision(17) << v;
    return oss.str();
}
}  // namespace

JsonHasher::JsonHasher(std::unique_ptr<Hasher> algo)
    : hasher_(std::move(algo)) {
    if (!hasher_)
        hasher_ = std::make_unique<DefaultHasher>();
}

std::string JsonHasher::hex() const {
    return hasher_->hex();
}

void JsonHasher::hash_object(json_t* obj) {
    hasher_->add_byte(0x01);  // tag objet
    std::vector<std::string> keys;
    const char* key;
    json_t* value;
    json_object_foreach(obj, key, value) { keys.emplace_back(key); }
    std::sort(keys.begin(), keys.end());

    for (const auto& k : keys) {
        hasher_->add_string(k);
        hash_value(json_object_get(obj, k.c_str()));
        hasher_->add_byte(0x7f);  // séparateur
    }
    hasher_->add_byte(0xff);  // fin objet
}

void JsonHasher::hash_array(json_t* arr) {
    hasher_->add_byte(0x02);  // tag tableau
    size_t idx = 0;
    json_t* value = nullptr;
    json_array_foreach(arr, idx, value) {
        hash_value(value);
        hasher_->add_byte(0x7e);  // séparateur
    }
    hasher_->add_byte(0xfe);  // fin tableau
}

void JsonHasher::hash_value(json_t* value) {
    if (json_is_object(value))
        return hash_object(value);
    if (json_is_array(value))
        return hash_array(value);
    if (json_is_string(value)) {
        hasher_->add_byte(0x03);
        hasher_->add_string(json_string_value(value));
    } else if (json_is_integer(value)) {
        hasher_->add_byte(0x04);
        hasher_->add_string(std::to_string(json_integer_value(value)));
    } else if (json_is_real(value)) {
        hasher_->add_byte(0x05);
        hasher_->add_string(real_to_string(json_real_value(value)));
    } else if (json_is_true(value)) {
        hasher_->add_byte(0x06);
        hasher_->add_byte(1);
    } else if (json_is_false(value)) {
        hasher_->add_byte(0x07);
        hasher_->add_byte(0);
    } else if (json_is_null(value)) {
        hasher_->add_byte(0x08);
    } else {
        hasher_->add_byte(0x09);  // type inconnu
    }
}

void JsonHasher::add(json_t* value) { hash_value(value); }

}  // namespace fragment
