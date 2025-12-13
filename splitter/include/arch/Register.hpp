#pragma once

#include <array>
#include <cstddef>
#include <string_view>

namespace splitter {

class RegisterCatalog;

class Register {
public:
    static constexpr std::size_t kCount = 42;

    Register() noexcept = default;
    Register(std::string_view name, bool call_clobbered = false) noexcept;

    [[nodiscard]] std::string_view Name() const noexcept;
    [[nodiscard]] bool IsCallClobbered() const noexcept;

    [[nodiscard]] static const std::array<Register, kCount>& All() noexcept;
    [[nodiscard]] static bool Contains(std::string_view candidate);
    [[nodiscard]] static bool IsCallClobbered(std::string_view candidate);

private:
    std::string_view name_;
    bool call_clobbered_ = false;
};

}  // namespace splitter
