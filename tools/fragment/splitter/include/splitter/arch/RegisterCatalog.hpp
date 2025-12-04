#pragma once

#include <array>
#include <string_view>
#include <unordered_map>

#include "splitter/arch/Register.hpp"

namespace splitter {

class RegisterCatalog {
public:
    static const RegisterCatalog& Instance();

    [[nodiscard]] const std::array<Register, Register::kCount>& All() const noexcept { return registers_; }
    [[nodiscard]] bool Contains(std::string_view candidate) const;
    [[nodiscard]] bool IsCallClobbered(std::string_view candidate) const;
    [[nodiscard]] const Register* Find(std::string_view name) const;

private:
    RegisterCatalog();

    std::array<Register, Register::kCount> registers_;
    std::unordered_map<std::string_view, const Register*, std::hash<std::string_view>, std::equal_to<>> lookup_;
};

}  // namespace splitter
