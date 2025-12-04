#pragma once

#include <array>
#include <cstddef>
#include <string_view>

namespace splitter {

class RegisterCatalog;

class Register {
public:
    static constexpr std::size_t kCount = 42;

    constexpr Register() noexcept = default;
    constexpr Register(std::string_view name, bool call_clobbered = false) noexcept
        : name_(name), call_clobbered_(call_clobbered) {}

    [[nodiscard]] constexpr std::string_view Name() const noexcept { return name_; }
    [[nodiscard]] constexpr bool IsCallClobbered() const noexcept { return call_clobbered_; }

    [[nodiscard]] static const std::array<Register, kCount>& All() noexcept;
    [[nodiscard]] static bool Contains(std::string_view candidate);
    [[nodiscard]] static bool IsCallClobbered(std::string_view candidate);

private:
    std::string_view name_;
    bool call_clobbered_ = false;
};

}  // namespace splitter
