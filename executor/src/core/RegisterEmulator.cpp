#include "core/Memory.hpp"

#include "support/Logging.hpp"
#include "support/Utils.hpp"

namespace fragment {

RegisterEmulator::RegisterEmulator() {
    memory.resize(1024 * 1024, 0);
    stack_base = memory.size() - 0x10000;
    regs64["rsp"] = stack_base;
    regs64["rbp"] = stack_base;
}

void RegisterEmulator::enable_patch_log(std::vector<MemoryPatch>& log) {
    patch_log = log;
}

void RegisterEmulator::disable_patch_log() {
    patch_log.reset();
}

PatchLogGuard::PatchLogGuard(RegisterEmulator& emu, std::vector<MemoryPatch>& log) : emulator(emu) {
    emulator.enable_patch_log(log);
}

PatchLogGuard::~PatchLogGuard() {
    emulator.disable_patch_log();
}

uint64_t RegisterEmulator::get(const std::string& reg) const {
    auto it = regs64.find(reg);
    if (it != regs64.end())
        return it->second;

    if (reg.size() == 3 && reg[0] == 'e') {
        std::string r64 = "r" + reg.substr(1);
        auto it64 = regs64.find(r64);
        if (it64 != regs64.end())
            return it64->second & 0xFFFFFFFFULL;
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
        if (it64 != regs64.end())
            it64->second = (it64->second & 0xFFFFFFFF00000000ULL) | (value & 0xFFFFFFFFULL);
    }
}

void RegisterEmulator::write_qword(uint64_t addr, uint64_t value) {
    constexpr size_t kWidth = sizeof(uint64_t);

    if (addr + kWidth > memory.size())
        return;

    std::array<uint8_t, kWidth> before{};
    std::memcpy(before.data(), &memory[addr], kWidth);

    std::array<uint8_t, kWidth> after{};
    std::memcpy(after.data(), &value, kWidth);

    if (patch_log && before != after) {
        MemoryPatch patch;

        patch.address = addr;
        patch.before.assign(before.begin(), before.end());
        patch.after.assign(after.begin(), after.end());
        patch_log->get().push_back(std::move(patch));
    }

    std::memcpy(&memory[addr], &value, kWidth);
}

uint64_t RegisterEmulator::read_qword(uint64_t addr) const {
    constexpr size_t kWidth = sizeof(uint64_t);

    if (addr + kWidth > memory.size())
        return 0;

    uint64_t value = 0;
    std::memcpy(&value, &memory[addr], kWidth);
    return value;
}

void RegisterEmulator::write_bytes(uint64_t addr, const std::vector<uint8_t>& bytes) {
    if (bytes.empty() || addr >= memory.size())
        return;

    size_t len = std::min(bytes.size(), memory.size() - addr);
    if (!len)
        return;

    std::vector<uint8_t> before(memory.begin() + addr, memory.begin() + addr + len);

    if (patch_log && before != std::vector<uint8_t>(bytes.begin(), bytes.begin() + len)) {
        MemoryPatch patch;
        patch.address = addr;
        patch.before = before;
        patch.after.assign(bytes.begin(), bytes.begin() + len);
        patch_log->get().push_back(std::move(patch));
    }

    std::copy(bytes.begin(), bytes.begin() + len, memory.begin() + addr);
}

std::vector<uint8_t> RegisterEmulator::read_bytes(uint64_t addr, std::size_t len) const {
    std::vector<uint8_t> out;
    if (!len || addr >= memory.size())
        return out;

    const std::size_t available = std::min<std::size_t>(len, memory.size() - addr);
    out.insert(out.end(), memory.begin() + addr, memory.begin() + addr + available);
    return out;
}

void RegisterEmulator::print_state() const {
    log::subsection("État des registres");

    for (const auto& [reg, val] : regs64) {
        std::cout << std::setw(4) << reg << " = 0x"
                  << std::hex << std::setw(16) << std::setfill('0') << val
                  << std::dec << std::setfill(' ') << " (" << val << ")";
        std::string ascii = ascii_from_uint64(val);
        if (!ascii.empty())
            std::cout << "  '" << ascii << "'";
        std::cout << "\n";
    }

    std::cout << "\nFlags: ZF=" << ZF << " SF=" << SF
              << " CF=" << CF << " OF=" << OF << "\n";
}

}  // namespace fragment
