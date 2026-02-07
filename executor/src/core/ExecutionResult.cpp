#include "core/ExecutionResult.hpp"

#include "support/Logging.hpp"
#include "support/Utils.hpp"

namespace fragment {

bool FdTable::empty() const {
    return entries_.empty();
}

size_t FdTable::size() const {
    return entries_.size();
}

const FdTable::Map& FdTable::entries() const {
    return entries_;
}

bool FdTable::contains(int fd) const {
    return entries_.count(fd) != 0;
}

void FdTable::set(int fd, FdCapture capture) {
    entries_[fd] = std::move(capture);
}

FdCapture& FdTable::operator[](int fd) {
    return entries_[fd];
}

const FdCapture& FdTable::at(int fd) const {
    return entries_.at(fd);
}

FdCapture& FdTable::at(int fd) {
    return entries_.at(fd);
}

size_t FdTable::count(int fd) const {
    return entries_.count(fd);
}

FdTable::Map::const_iterator FdTable::begin() const {
    return entries_.begin();
}

FdTable::Map::const_iterator FdTable::end() const {
    return entries_.end();
}

static void print_registers(const std::map<std::string, uint64_t>& initial,
                            const std::map<std::string, uint64_t>& final) {
    constexpr std::string_view RESET = "\033[0m";
    constexpr std::string_view GREEN = "\033[32m";
    constexpr std::string_view CYAN = "\033[36m";

    log::subsection("Registres (initial -> final)");

    for (const auto& [reg, final_value] : final) {
        auto init_it = initial.find(reg);
        uint64_t init_value = (init_it == initial.end()) ? 0 : init_it->second;
        bool changed = (init_value != final_value);
        std::string_view color = changed ? GREEN : CYAN;

        std::string ascii_before = ascii_from_uint64(init_value);
        std::string ascii_after = ascii_from_uint64(final_value);

        std::cout << color
                  << std::setw(4) << reg << RESET << ": "
                  << "0x" << std::hex << std::setw(16) << std::setfill('0') << init_value
                  << " -> 0x" << std::setw(16) << final_value
                  << std::dec << std::setfill(' ');

        if (!ascii_before.empty() || !ascii_after.empty())
            std::cout << "  ('" << (ascii_before.empty() ? "" : ascii_before)
                      << "' -> '" << (ascii_after.empty() ? "" : ascii_after) << "')";

        if (changed)
            std::cout << " *";

        std::cout << "\n";
    }
}

static std::string format_bytes(const std::vector<uint8_t>& bytes,
                                const std::vector<uint8_t>& other,
                                std::string_view color) {
    constexpr std::string_view RESET = "\033[0m";
    constexpr std::string_view DIM = "\033[90m";

    std::ostringstream oss;
    for (size_t i = 0; i < bytes.size(); ++i) {
        if (i)
            oss << ' ';
        bool changed = i >= other.size() || bytes[i] != other[i];
        std::string_view prefix = changed ? color : DIM;
        oss << prefix << std::hex << std::setw(2) << std::setfill('0')
            << static_cast<int>(bytes[i]) << RESET;
        if ((i + 1) % 16 == 0 && i + 1 < bytes.size())
            oss << "\n              ";
    }

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

static void print_program_stderr(const ExecutionResult& result) {
    if (result.program_stderr.empty())
        return;

    log::subsection("Sortie erreur du fragment");

    std::cout << result.program_stderr;
    if (result.program_stderr.back() != '\n')
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

    print_registers(initial_regs, final_regs);
    print_memory_patches(*this);
    print_program_stdout(*this);
    print_program_stderr(*this);
    if (!fd_outputs.empty()) {
        log::subsection("FDs capturés");
        for (const auto& [fd, cap] : fd_outputs) {
            std::cout << "  fd " << fd;
            if (!cap.alias.empty())
                std::cout << " (" << cap.alias << ")";
            std::cout << " : " << cap.data.size() << " octets\n";
        }
    }
}

}  // namespace fragment
