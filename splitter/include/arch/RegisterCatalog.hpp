#pragma once

#include <array>
#include <cstddef>
#include <functional>
#include <optional>
#include <string_view>
#include <unordered_map>

#include "arch/Register.hpp"

namespace splitter {

class RegisterCatalog {
public:
    static const RegisterCatalog& Instance();

    [[nodiscard]] const std::array<Register, Register::kCount>& All() const noexcept;
    [[nodiscard]] bool Contains(std::string_view candidate) const;
    [[nodiscard]] bool IsCallClobbered(std::string_view candidate) const;
    [[nodiscard]] std::optional<std::reference_wrapper<const Register>> Find(std::string_view name) const;

private:
    RegisterCatalog();

    std::array<Register, Register::kCount> registers_;
    std::unordered_map<std::string_view, std::size_t, std::hash<std::string_view>, std::equal_to<>> lookup_;
};

}  // namespace splitter
