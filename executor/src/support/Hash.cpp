#include "support/Hash.hpp"

#include <sstream>
#include <iomanip>

namespace fragment {

Fnv1aHasher::Fnv1aHasher() : state_(0xcbf29ce484222325ULL) {}

void Fnv1aHasher::reset() { state_ = 0xcbf29ce484222325ULL; }

void Fnv1aHasher::add_byte(uint8_t b) {
    state_ ^= static_cast<uint64_t>(b);
    state_ *= 0x100000001b3ULL;
}

void Fnv1aHasher::add_string(std::string_view s) {
    for (unsigned char c : s)
        add_byte(c);
    add_byte(0xff);
}

void Fnv1aHasher::add_uint64(uint64_t v) {
    for (int i = 0; i < 8; ++i)
        add_byte(static_cast<uint8_t>((v >> (i * 8)) & 0xff));
    add_byte(0xfe);
}

void Fnv1aHasher::add_bool(bool v) {
    add_byte(v ? 0x01 : 0x00);
    add_byte(0xfd);
}

std::string Fnv1aHasher::hex() const {
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << state_;
    return oss.str();
}

namespace {
constexpr uint64_t kStdSeed = 0x9e3779b97f4a7c15ULL;
}

StdHasher::StdHasher() : state_(kStdSeed) {}

void StdHasher::reset() { state_ = kStdSeed; }

void StdHasher::mix(uint64_t value) {
    state_ ^= value + kStdSeed + (state_ << 6) + (state_ >> 2);
    state_ = (state_ << 13) | (state_ >> (64 - 13));
}

void StdHasher::add_byte(uint8_t b) {
    mix(static_cast<uint64_t>(b));
}

void StdHasher::add_string(std::string_view s) {
    for (unsigned char c : s)
        add_byte(c);
    add_byte(0xfe);
}

void StdHasher::add_uint64(uint64_t v) {
    mix(v);
    add_byte(0xfd);
}

void StdHasher::add_bool(bool v) {
    add_byte(v ? 1 : 0);
    add_byte(0xfc);
}

std::string StdHasher::hex() const {
    std::ostringstream oss;
    oss << std::hex << std::setw(16) << std::setfill('0') << state_;
    return oss.str();
}

DomainHasher::DomainHasher(std::string_view domain, std::unique_ptr<Hasher> algo)
    : domain_(domain), algo_(std::move(algo)) {
    if (!algo_)
        algo_ = std::make_unique<DefaultHasher>();
    prefix();
}

void DomainHasher::prefix() {
    algo_->reset();
    algo_->add_string(domain_);
    algo_->add_byte(0xa5);
}

void DomainHasher::reset() {
    prefix();
}

void DomainHasher::add_byte(uint8_t b) {
    algo_->add_byte(b);
}

void DomainHasher::add_string(std::string_view s) {
    algo_->add_string(s);
}

void DomainHasher::add_uint64(uint64_t v) {
    algo_->add_uint64(v);
}

void DomainHasher::add_bool(bool v) {
    algo_->add_bool(v);
}

std::string DomainHasher::hex() const {
    return algo_->hex();
}

}  // namespace fragment
