#include "pipeline/BinaryPath.hpp"

namespace splitter {

BinaryPath::BinaryPath(std::string value)
: value_(std::move(value)) {}

const std::string& BinaryPath::Value() const noexcept {
    return value_;
}

bool BinaryPath::Empty() const noexcept {
    return value_.empty();
}

}  // namespace splitter
