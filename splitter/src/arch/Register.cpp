#include "arch/Register.hpp"

namespace splitter {

Register::Register(std::string_view name, bool call_clobbered) noexcept
    : name_(name), call_clobbered_(call_clobbered) {}

std::string_view Register::Name() const noexcept {
    return name_;
}

bool Register::IsCallClobbered() const noexcept {
    return call_clobbered_;
}

}  // namespace splitter
