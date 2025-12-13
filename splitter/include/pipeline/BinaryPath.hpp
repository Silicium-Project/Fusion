#pragma once

#include <string>

namespace splitter {

class BinaryPath {
public:
    BinaryPath() = default;
    explicit BinaryPath(std::string value);

    const std::string& Value() const noexcept;
    bool Empty() const noexcept;

private:
    std::string value_;
};

}  // namespace splitter
