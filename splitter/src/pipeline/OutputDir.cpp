#include "pipeline/OutputDir.hpp"

namespace splitter {

OutputDir::OutputDir(std::string value)
: value_(std::move(value)) {}

const std::string& OutputDir::Value() const noexcept {
    return value_;
}

bool OutputDir::Empty() const noexcept {
    return value_.empty();
}

}  // namespace splitter
