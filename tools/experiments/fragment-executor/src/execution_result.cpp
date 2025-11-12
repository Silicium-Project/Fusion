#include "fragment/execution_result.hpp"

#include "fragment/logging.hpp"
#include "fragment/utils.hpp"

namespace fragment {

static void print_changed_registers(const ExecutionResult& result) {
    if (result.changed_regs.empty())
        return;

    log::subsection("Registres modifiés");

    for (const auto& [reg, vals] : result.changed_regs) {
        std::string ascii_before = ascii_from_uint64(vals.first);
        std::string ascii_after = ascii_from_uint64(vals.second);

        std::cout << std::setw(4) << reg << ": "
                  << "0x" << std::hex << std::setw(16) << std::setfill('0') << vals.first
                  << " -> 0x" << std::setw(16) << vals.second
                  << std::dec << std::setfill(' ');

        if (!ascii_before.empty() || !ascii_after.empty())
            std::cout << "  ('" << (ascii_before.empty() ? "" : ascii_before)
                      << "' -> '" << (ascii_after.empty() ? "" : ascii_after) << "')";

        std::cout << "\n";
    }
}

static std::string format_bytes(const std::vector<uint8_t>& bytes,
                                const std::vector<uint8_t>& other,
                                std::string_view color) {
    constexpr std::string_view RESET = "\033[0m";
    constexpr std::string_view DIM = "\033[90m";

    std::ostringstream oss;
    size_t limit = std::min<size_t>(bytes.size(), 16);

    for (size_t i = 0; i < limit; ++i) {
        if (i)
            oss << ' ';
        bool changed = i >= other.size() || bytes[i] != other[i];
        std::string_view prefix = changed ? color : DIM;
        oss << prefix << std::hex << std::setw(2) << std::setfill('0')
            << static_cast<int>(bytes[i]) << RESET;
    }

    if (bytes.size() > limit)
        oss << " ...";

    return oss.str();
}

static void print_memory_patches(const ExecutionResult& result) {
    if (result.memory_patches.empty())
        return;

    constexpr std::string_view RED = "\033[31m";
    constexpr std::string_view GREEN = "\033[32m";

    log::subsection("Modifications mémoire (type diff)");

    for (const auto& patch : result.memory_patches) {
        std::cout << " @0x" << std::hex << patch.address << std::dec
                  << " (" << patch.before.size() << " bytes)\n";
        std::cout << "    - avant : [" << format_bytes(patch.before, patch.after, RED) << "]\n";
        std::cout << "    + après : [" << format_bytes(patch.after, patch.before, GREEN) << "]\n";
    }
}

static void print_program_stdout(const ExecutionResult& result) {
    if (result.program_stdout.empty())
        return;

    log::subsection("Sortie standard du fragment");

    std::cout << result.program_stdout;
    if (result.program_stdout.back() != '\n')
        std::cout << "\n";
}

void ExecutionResult::print() const {
    if (!success) {
        log::error(std::string("Exécution échouée: ") + error_message);
        return;
    }

    log::info("Exécution réussie");
    std::cout << "Instructions exécutées: " << instructions_executed << "\n";
    std::cout << "Accès mémoire: " << memory_accesses << "\n";

    print_changed_registers(*this);
    print_memory_patches(*this);
    print_program_stdout(*this);
}

}  // namespace fragment
