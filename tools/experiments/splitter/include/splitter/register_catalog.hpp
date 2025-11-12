#pragma once

#include <array>
#include <string_view>
#include <unordered_map>

#include "splitter/register.hpp"

namespace splitter {

    class RegisterCatalog {
    public:
        static const RegisterCatalog& instance();

        [[nodiscard]] const std::array<Register, Register::kCount>& all() const noexcept {
            return registers_;
        }

        [[nodiscard]] bool contains(std::string_view candidate) const;
        [[nodiscard]] bool is_call_clobbered(std::string_view candidate) const;
        [[nodiscard]] const Register* find(std::string_view name) const;

    private:
        RegisterCatalog();

        std::array<Register, Register::kCount> registers_;
        std::unordered_map<std::string_view, const Register*, std::hash<std::string_view>, std::equal_to<>> lookup_;
    };

    inline const RegisterCatalog& RegisterCatalog::instance() {
        static const RegisterCatalog catalog;
        return catalog;
    }

    inline RegisterCatalog::RegisterCatalog()
    : registers_{{
        Register("rax", true),  Register("rbx"),        Register("rcx", true),
        Register("rdx", true),  Register("rsi"),        Register("rdi"),
        Register("rsp"),        Register("rbp"),        Register("r8", true),
        Register("r9", true),   Register("r10", true),  Register("r11", true),
        Register("r12"),        Register("r13"),        Register("r14"),
        Register("r15"),        Register("eax"),        Register("ebx"),
        Register("ecx"),        Register("edx"),        Register("esi"),
        Register("edi"),        Register("esp"),        Register("ebp"),
        Register("al"),         Register("ah"),         Register("bl"),
        Register("bh"),         Register("cl"),         Register("ch"),
        Register("dl"),         Register("dh"),         Register("sil"),
        Register("dil"),        Register("xmm0"),       Register("xmm1"),
        Register("xmm2"),       Register("xmm3"),       Register("xmm4"),
        Register("xmm5"),       Register("xmm6"),       Register("xmm7")
    }} {
        lookup_.reserve(registers_.size());
        for (const auto& reg : registers_)
            lookup_.emplace(reg.name(), &reg);
    }

    inline const Register* RegisterCatalog::find(std::string_view name) const {
        auto it = lookup_.find(name);
        return (it == lookup_.end()) ? nullptr : it->second;
    }

    inline bool RegisterCatalog::contains(std::string_view candidate) const {
        return find(candidate) != nullptr;
    }

    inline bool RegisterCatalog::is_call_clobbered(std::string_view candidate) const {
        auto reg = find(candidate);
        return reg != nullptr && reg->is_call_clobbered();
    }

    inline const std::array<Register, Register::kCount>& Register::all() noexcept {
        return RegisterCatalog::instance().all();
    }

    inline bool Register::contains(std::string_view candidate) {
        return RegisterCatalog::instance().contains(candidate);
    }

    inline bool Register::is_call_clobbered(std::string_view candidate) {
        return RegisterCatalog::instance().is_call_clobbered(candidate);
    }

}  // namespace splitter
