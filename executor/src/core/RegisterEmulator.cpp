#include "core/Memory.hpp"

#include "support/Logging.hpp"
#include "support/Utils.hpp"

#include <cctype>
#include <optional>

namespace fragment {

RegisterEmulator::RegisterEmulator() {
    constexpr uint64_t kDefaultMemorySize = 1024 * 1024;
    constexpr uint64_t kStackReserve = 0x10000;
    stack_base = kDefaultMemorySize - kStackReserve;
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

    auto reg_alias = [&](const std::string& base, size_t width, size_t shift) -> std::optional<uint64_t> {
        auto it64 = regs64.find(base);
        if (it64 == regs64.end())
            return std::nullopt;
        const uint64_t mask = (width >= 8) ? ~0ULL : ((1ULL << (width * 8)) - 1ULL);
        return (it64->second >> shift) & mask;
    };

    const std::string r = reg;
    if (r == "al") return reg_alias("rax", 1, 0).value_or(0);
    if (r == "ah") return reg_alias("rax", 1, 8).value_or(0);
    if (r == "ax") return reg_alias("rax", 2, 0).value_or(0);
    if (r == "bl") return reg_alias("rbx", 1, 0).value_or(0);
    if (r == "bh") return reg_alias("rbx", 1, 8).value_or(0);
    if (r == "bx") return reg_alias("rbx", 2, 0).value_or(0);
    if (r == "cl") return reg_alias("rcx", 1, 0).value_or(0);
    if (r == "ch") return reg_alias("rcx", 1, 8).value_or(0);
    if (r == "cx") return reg_alias("rcx", 2, 0).value_or(0);
    if (r == "dl") return reg_alias("rdx", 1, 0).value_or(0);
    if (r == "dh") return reg_alias("rdx", 1, 8).value_or(0);
    if (r == "dx") return reg_alias("rdx", 2, 0).value_or(0);
    if (r == "sil") return reg_alias("rsi", 1, 0).value_or(0);
    if (r == "si") return reg_alias("rsi", 2, 0).value_or(0);
    if (r == "dil") return reg_alias("rdi", 1, 0).value_or(0);
    if (r == "di") return reg_alias("rdi", 2, 0).value_or(0);
    if (r == "bpl") return reg_alias("rbp", 1, 0).value_or(0);
    if (r == "bp") return reg_alias("rbp", 2, 0).value_or(0);
    if (r == "spl") return reg_alias("rsp", 1, 0).value_or(0);
    if (r == "sp") return reg_alias("rsp", 2, 0).value_or(0);

    auto get_extended = [&](char suffix, size_t width) -> std::optional<uint64_t> {
        if (r.size() < 3 || r[0] != 'r' || r.back() != suffix)
            return std::nullopt;
        const std::string num = r.substr(1, r.size() - 2);
        if (num.empty() || num.size() > 2)
            return std::nullopt;
        for (char c : num) {
            if (!std::isdigit(static_cast<unsigned char>(c)))
                return std::nullopt;
        }
        const int idx = std::stoi(num);
        if (idx < 8 || idx > 15)
            return std::nullopt;
        const std::string base = "r" + num;
        return reg_alias(base, width, 0);
    };

    if (auto v = get_extended('b', 1)) return *v;
    if (auto v = get_extended('w', 2)) return *v;

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

    auto set_alias = [&](const std::string& base, size_t width, size_t shift) {
        uint64_t& base_val = regs64[base];
        const uint64_t mask = (width >= 8) ? ~0ULL : ((1ULL << (width * 8)) - 1ULL);
        const uint64_t cleared = base_val & ~(mask << shift);
        base_val = cleared | ((value & mask) << shift);
    };

    const std::string r = reg;
    if (r == "al") { set_alias("rax", 1, 0); return; }
    if (r == "ah") { set_alias("rax", 1, 8); return; }
    if (r == "ax") { set_alias("rax", 2, 0); return; }
    if (r == "bl") { set_alias("rbx", 1, 0); return; }
    if (r == "bh") { set_alias("rbx", 1, 8); return; }
    if (r == "bx") { set_alias("rbx", 2, 0); return; }
    if (r == "cl") { set_alias("rcx", 1, 0); return; }
    if (r == "ch") { set_alias("rcx", 1, 8); return; }
    if (r == "cx") { set_alias("rcx", 2, 0); return; }
    if (r == "dl") { set_alias("rdx", 1, 0); return; }
    if (r == "dh") { set_alias("rdx", 1, 8); return; }
    if (r == "dx") { set_alias("rdx", 2, 0); return; }
    if (r == "sil") { set_alias("rsi", 1, 0); return; }
    if (r == "si") { set_alias("rsi", 2, 0); return; }
    if (r == "dil") { set_alias("rdi", 1, 0); return; }
    if (r == "di") { set_alias("rdi", 2, 0); return; }
    if (r == "bpl") { set_alias("rbp", 1, 0); return; }
    if (r == "bp") { set_alias("rbp", 2, 0); return; }
    if (r == "spl") { set_alias("rsp", 1, 0); return; }
    if (r == "sp") { set_alias("rsp", 2, 0); return; }

    auto set_extended = [&](char suffix, size_t width) -> bool {
        if (r.size() < 3 || r[0] != 'r' || r.back() != suffix)
            return false;
        const std::string num = r.substr(1, r.size() - 2);
        if (num.empty() || num.size() > 2)
            return false;
        for (char c : num) {
            if (!std::isdigit(static_cast<unsigned char>(c)))
                return false;
        }
        const int idx = std::stoi(num);
        if (idx < 8 || idx > 15)
            return false;
        const std::string base = "r" + num;
        set_alias(base, width, 0);
        return true;
    };

    if (set_extended('b', 1) || set_extended('w', 2))
        return;

    if (reg.size() == 3 && reg[0] == 'e') {
        std::string r64 = "r" + reg.substr(1);
        auto it64 = regs64.find(r64);
        if (it64 != regs64.end())
            it64->second = (it64->second & 0xFFFFFFFF00000000ULL) | (value & 0xFFFFFFFFULL);
    }
}

void RegisterEmulator::write_qword(uint64_t addr, uint64_t value) {
    constexpr size_t kWidth = sizeof(uint64_t);

    std::array<uint8_t, kWidth> after{};
    std::memcpy(after.data(), &value, kWidth);
    write_bytes(addr, std::vector<uint8_t>(after.begin(), after.end()));
}

uint64_t RegisterEmulator::read_qword(uint64_t addr) const {
    constexpr size_t kWidth = sizeof(uint64_t);

    auto bytes = read_bytes(addr, kWidth);
    if (bytes.size() != kWidth)
        return 0;

    uint64_t value = 0;
    std::memcpy(&value, bytes.data(), kWidth);
    return value;
}

void RegisterEmulator::write_bytes(uint64_t addr, const std::vector<uint8_t>& bytes) {
    if (bytes.empty())
        return;

    const size_t len = bytes.size();
    std::vector<uint8_t> before;
    before.reserve(len);
    for (size_t i = 0; i < len; ++i) {
        const uint64_t current = addr + i;
        auto it = memory.find(current);
        if (it != memory.end())
            before.push_back(it->second);
        else
            before.push_back(0);
    }

    if (patch_log && before != bytes) {
        MemoryPatch patch;
        patch.address = addr;
        patch.before = before;
        patch.after = bytes;
        patch_log->get().push_back(std::move(patch));
    }

    for (size_t i = 0; i < len; ++i)
        memory[addr + i] = bytes[i];
}

std::vector<uint8_t> RegisterEmulator::read_bytes(uint64_t addr, std::size_t len) const {
    std::vector<uint8_t> out;
    if (!len)
        return out;

    constexpr uint64_t kDefaultMemorySize = 1024 * 1024;
    out.reserve(len);
    for (size_t i = 0; i < len; ++i) {
        const uint64_t current = addr + i;
        auto it = memory.find(current);
        if (it != memory.end()) {
            out.push_back(it->second);
            continue;
        }
        if (current < kDefaultMemorySize) {
            out.push_back(0);
            continue;
        }
        return {};
    }
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
