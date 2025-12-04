#include "splitter/arch/RegisterCatalog.hpp"

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
    for (const auto& reg : registers_)
        lookup_.emplace(reg.Name(), &reg);
}

const Register* RegisterCatalog::Find(std::string_view name) const {
    auto it = lookup_.find(name);
    return (it == lookup_.end()) ? nullptr : it->second;
}

bool RegisterCatalog::Contains(std::string_view candidate) const {
    return Find(candidate) != nullptr;
}

bool RegisterCatalog::IsCallClobbered(std::string_view candidate) const {
    auto reg = Find(candidate);
    return reg != nullptr && reg->IsCallClobbered();
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
