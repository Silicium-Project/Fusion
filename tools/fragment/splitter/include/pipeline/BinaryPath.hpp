#pragma once

#include <string>

namespace splitter {

class BinaryPath {
public:
    BinaryPath() = default;
    explicit BinaryPath(std::string value) : value_(std::move(value)) {}

    const std::string& Value() const noexcept { return value_; }
    bool Empty() const noexcept { return value_.empty(); }

private:
    std::string value_;
};

}  // namespace splitter
