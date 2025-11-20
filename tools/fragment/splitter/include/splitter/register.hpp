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
        : name_(name)
        , call_clobbered_(call_clobbered) {}

        [[nodiscard]] constexpr std::string_view name() const noexcept {
            return name_;
        }

        [[nodiscard]] constexpr bool is_call_clobbered() const noexcept {
            return call_clobbered_;
        }

        [[nodiscard]] static const std::array<Register, kCount>& all() noexcept;
        [[nodiscard]] static bool contains(std::string_view candidate);
        [[nodiscard]] static bool is_call_clobbered(std::string_view candidate);

    private:
        std::string_view name_;
        bool call_clobbered_ = false;
    };

}  // namespace splitter

