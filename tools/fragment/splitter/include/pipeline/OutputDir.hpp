#pragma once

#include <string>

namespace splitter {

class OutputDir {
public:
    OutputDir() = default;
    explicit OutputDir(std::string value) : value_(std::move(value)) {}

    const std::string& Value() const noexcept { return value_; }
    bool Empty() const noexcept { return value_.empty(); }

private:
    std::string value_;
};

}  // namespace splitter
