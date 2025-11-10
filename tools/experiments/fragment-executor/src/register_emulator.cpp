#include "fragment/memory.hpp"

#include <algorithm>

#include "fragment/utils.hpp"

namespace fragment {

uint64_t RegisterEmulator::get(const std::string& reg) const {
    auto it = regs64.find(reg);
    if (it != regs64.end()) return it->second;
    if (reg.size() == 3 && reg[0] == 'e') {
        std::string r64 = "r" + reg.substr(1);
        auto it64 = regs64.find(r64);
        if (it64 != regs64.end()) {
            return it64->second & 0xFFFFFFFFULL;
        }
    }
    return 0;
}

void RegisterEmulator::set(const std::string& reg, uint64_t value) {
    auto it = regs64.find(reg);
    if (it != regs64.end()) {
        it->second = value;
        return;
    }
    if (reg.size() == 3 && reg[0] == 'e') {
        std::string r64 = "r" + reg.substr(1);
        auto it64 = regs64.find(r64);
        if (it64 != regs64.end()) {
            it64->second = (it64->second & 0xFFFFFFFF00000000ULL) | (value & 0xFFFFFFFFULL);
        }
    }
}

void RegisterEmulator::write_memory(uint64_t addr, const void* data, size_t size) {
    if (addr + size > memory.size()) return;
    if (patch_log && size > 0) {
        std::vector<uint8_t> before(size);
        std::memcpy(before.data(), &memory[addr], size);
        if (std::memcmp(before.data(), data, size) != 0) {
            MemoryPatch patch;
            patch.address = addr;
            patch.before = std::move(before);
            patch.after.assign(static_cast<const uint8_t*>(data),
                               static_cast<const uint8_t*>(data) + size);
            patch_log->push_back(std::move(patch));
        }
    }
    std::memcpy(&memory[addr], data, size);
}

void RegisterEmulator::read_memory(uint64_t addr, void* data, size_t size) const {
    if (addr + size <= memory.size()) {
        std::memcpy(data, &memory[addr], size);
    }
}

void RegisterEmulator::print_state() const {
    std::cout << "\n=== État des registres ===\n";
    for (const auto& [reg, val] : regs64) {
        std::cout << std::setw(4) << reg << " = 0x"
                  << std::hex << std::setw(16) << std::setfill('0') << val
                  << std::dec << std::setfill(' ') << " (" << val << ")";
        std::string ascii = ascii_from_uint64(val);
        if (!ascii.empty()) {
            std::cout << "  '" << ascii << "'";
        }
        std::cout << "\n";
    }
    std::cout << "\nFlags: ZF=" << ZF << " SF=" << SF
              << " CF=" << CF << " OF=" << OF << "\n";
}

}  // namespace fragment
