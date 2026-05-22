#include "arch/RegisterCatalog.hpp"

namespace splitter {

const RegisterCatalog& RegisterCatalog::Instance() {
    static const RegisterCatalog catalog;
    return catalog;
}

RegisterCatalog::RegisterCatalog()
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
          Register("xmm5"),       Register("xmm6"),       Register("xmm7")}} {
    lookup_.reserve(registers_.size());
    for (std::size_t idx = 0; idx < registers_.size(); ++idx)
        lookup_.emplace(registers_[idx].Name(), idx);
}

const std::array<Register, Register::kCount>& RegisterCatalog::All() const noexcept {
    return registers_;
}

std::optional<std::reference_wrapper<const Register>> RegisterCatalog::Find(std::string_view name) const {
    auto it = lookup_.find(name);
    if (it == lookup_.end())
        return std::nullopt;
    return std::cref(registers_[it->second]);
}

bool RegisterCatalog::Contains(std::string_view candidate) const {
    return Find(candidate).has_value();
}

bool RegisterCatalog::IsCallClobbered(std::string_view candidate) const {
    auto reg = Find(candidate);
    return reg.has_value() && reg->get().IsCallClobbered();
}

const std::array<Register, Register::kCount>& Register::All() noexcept {
    return RegisterCatalog::Instance().All();
}

bool Register::Contains(std::string_view candidate) {
    return RegisterCatalog::Instance().Contains(candidate);
}

bool Register::IsCallClobbered(std::string_view candidate) {
    return RegisterCatalog::Instance().IsCallClobbered(candidate);
}

}  // namespace splitter
