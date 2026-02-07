#pragma once

#include "core/Common.hpp"

#include <unordered_map>

namespace fragment {

struct MemoryPatch {
    uint64_t address = 0;
    std::vector<uint8_t> before;
    std::vector<uint8_t> after;
};

class RegisterEmulator {
public:
    std::map<std::string, uint64_t> regs64 = {
        {"rax", 0}, {"rbx", 0}, {"rcx", 0}, {"rdx", 0},
        {"rsi", 0}, {"rdi", 0}, {"rsp", 0}, {"rbp", 0},
        {"r8", 0},  {"r9", 0},  {"r10", 0}, {"r11", 0},
        {"r12", 0}, {"r13", 0}, {"r14", 0}, {"r15", 0}
    };

    bool ZF = false;
    bool SF = false;
    bool CF = false;
    bool OF = false;

    std::unordered_map<uint64_t, uint8_t> memory;
    uint64_t stack_base = 0;

    RegisterEmulator();

    uint64_t get(const std::string& reg) const;

    void set(const std::string& reg, uint64_t value);

    void write_qword(uint64_t addr, uint64_t value);

    uint64_t read_qword(uint64_t addr) const;

        void write_bytes(uint64_t addr, const std::vector<uint8_t>& bytes);
        std::vector<uint8_t> read_bytes(uint64_t addr, std::size_t len) const;

    void enable_patch_log(std::vector<MemoryPatch>& log);

    void disable_patch_log();

    void print_state() const;

private:
    std::optional<std::reference_wrapper<std::vector<MemoryPatch>>> patch_log;
};

class PatchLogGuard {
public:
    PatchLogGuard(RegisterEmulator& emu, std::vector<MemoryPatch>& log);
    ~PatchLogGuard();

private:
    RegisterEmulator& emulator;
};

}  // namespace fragment
