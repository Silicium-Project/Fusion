#pragma once

#include <string>

namespace splitter {

class OutputDir {
public:
    OutputDir() = default;
    explicit OutputDir(std::string value);

    const std::string& Value() const noexcept;
    bool Empty() const noexcept;

private:
    std::string value_;
};

}  // namespace splitter
