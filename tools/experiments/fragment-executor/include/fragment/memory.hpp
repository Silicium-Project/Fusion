#pragma once

#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <string>
#include <vector>

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

    std::vector<uint8_t> memory;
    uint64_t stack_base = 0;

    RegisterEmulator() {
        memory.resize(1024 * 1024, 0);
        stack_base = memory.size() - 0x10000;
        regs64["rsp"] = stack_base;
        regs64["rbp"] = stack_base;
    }

    uint64_t get(const std::string& reg) const;
    void set(const std::string& reg, uint64_t value);
    void write_memory(uint64_t addr, const void* data, size_t size);
    void read_memory(uint64_t addr, void* data, size_t size) const;
    void set_patch_log(std::vector<MemoryPatch>* log) { patch_log = log; }
    void print_state() const;

private:
    std::vector<MemoryPatch>* patch_log = nullptr;
};

class PatchLogGuard {
public:
    PatchLogGuard(RegisterEmulator& emu, std::vector<MemoryPatch>* log) : emulator(emu) {
        emulator.set_patch_log(log);
    }
    ~PatchLogGuard() { emulator.set_patch_log(nullptr); }

private:
    RegisterEmulator& emulator;
};

}  // namespace fragment
