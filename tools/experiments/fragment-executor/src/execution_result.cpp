#include "fragment/execution_result.hpp"

#include <iomanip>
#include <iostream>

#include "fragment/utils.hpp"

namespace fragment {

void ExecutionResult::print() const {
    if (!success) {
        std::cout << "❌ Exécution échouée: " << error_message << "\n";
        return;
    }
    std::cout << "✅ Exécution réussie\n";
    std::cout << "Instructions exécutées: " << instructions_executed << "\n";
    std::cout << "Accès mémoire: " << memory_accesses << "\n";

    if (!changed_regs.empty()) {
        std::cout << "\n=== Registres modifiés ===\n";
        for (const auto& [reg, vals] : changed_regs) {
            std::string ascii_before = ascii_from_uint64(vals.first);
            std::string ascii_after = ascii_from_uint64(vals.second);
            std::cout << std::setw(4) << reg << ": "
                      << "0x" << std::hex << std::setw(16) << std::setfill('0') << vals.first
                      << " → 0x" << std::setw(16) << vals.second
                      << std::dec << std::setfill(' ');
            if (!ascii_before.empty() || !ascii_after.empty()) {
                std::cout << "  ('" << (ascii_before.empty() ? "" : ascii_before)
                          << "' → '" << (ascii_after.empty() ? "" : ascii_after) << "')";
            }
            std::cout << "\n";
        }
    }

    if (!memory_patches.empty()) {
        std::cout << "\n=== Modifications mémoire (type diff) ===\n";
        const char* RESET = "\033[0m";
        const char* RED = "\033[31m";
        const char* GREEN = "\033[32m";
        const char* DIM = "\033[90m";
        for (const auto& patch : memory_patches) {
            auto format_bytes = [&](const std::vector<uint8_t>& bytes,
                                    const std::vector<uint8_t>& other,
                                    const char* color) {
                std::ostringstream oss;
                size_t limit = std::min<size_t>(bytes.size(), 16);
                for (size_t i = 0; i < limit; ++i) {
                    if (i) oss << ' ';
                    bool changed = (i >= other.size()) || bytes[i] != other[i];
                    const char* prefix = changed ? color : DIM;
                    if (i < bytes.size()) {
                        oss << prefix << std::hex << std::setw(2) << std::setfill('0')
                            << static_cast<int>(bytes[i]) << RESET;
                    } else {
                        oss << prefix << "--" << RESET;
                    }
                }
                if (bytes.size() > limit) {
                    oss << " …";
                }
                return oss.str();
            };
            std::cout << " @0x" << std::hex << patch.address << std::dec
                      << " (" << patch.before.size() << " bytes)\n";
            std::cout << "    - avant : ["
                      << format_bytes(patch.before, patch.after, RED) << "]\n";
            std::cout << "    + après : ["
                      << format_bytes(patch.after, patch.before, GREEN) << "]\n";
        }
    }

    if (!program_stdout.empty()) {
        std::cout << "\n=== Sortie standard du fragment ===\n";
        std::cout << program_stdout;
        if (program_stdout.back() != '\n') {
            std::cout << "\n";
        }
    }
}

}  // namespace fragment
