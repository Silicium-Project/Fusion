#include "fragment/fragment_executor.hpp"

#ifdef __linux__
#include <sys/mman.h>
#include <unistd.h>
#endif

#include <limits>

#include "fragment/logging.hpp"
#include "fragment/utils.hpp"

namespace fragment {

namespace {

constexpr size_t kNativeAlignment = 0x1000;

size_t align_up(size_t value, size_t alignment) {
    if (!alignment)
        return value;
    size_t remainder = value % alignment;
    if (!remainder)
        return value;
    if (value > std::numeric_limits<size_t>::max() - (alignment - remainder))
        return value;
    return value + (alignment - remainder);
}

struct NativeLayout {
    uint64_t base = 0;
    size_t span = 0;
};

std::optional<NativeLayout> compute_native_layout(
        uint64_t entry_address,
        size_t code_size,
        const std::map<uint64_t, std::vector<uint8_t>>& chunks) {
    if (!code_size)
        return std::nullopt;

    uint64_t min_addr = entry_address;
    uint64_t max_addr = entry_address + static_cast<uint64_t>(code_size);

    for (const auto& [addr, bytes] : chunks) {
        if (bytes.empty())
            continue;
        if (addr < min_addr)
            min_addr = addr;
        uint64_t end = addr + static_cast<uint64_t>(bytes.size());
        if (end > max_addr)
            max_addr = end;
    }

    if (max_addr <= min_addr)
        max_addr = min_addr + static_cast<uint64_t>(code_size);

    NativeLayout layout;
    layout.base = min_addr;
    layout.span = static_cast<size_t>(max_addr - min_addr);
    if (!layout.span)
        layout.span = code_size;
    return layout;
}

void copy_into_layout(uint8_t* base_ptr,
                      size_t buffer_size,
                      uint64_t layout_base,
                      uint64_t target_addr,
                      const std::vector<uint8_t>& bytes) {
    if (bytes.empty() || target_addr < layout_base)
        return;
    uint64_t offset64 = target_addr - layout_base;
    if (offset64 >= buffer_size)
        return;
    size_t offset = static_cast<size_t>(offset64);
    size_t available = buffer_size - offset;
    size_t len = std::min(available, bytes.size());
    if (!len)
        return;
    std::memcpy(base_ptr + offset, bytes.data(), len);
}

}  // namespace

static bool should_skip_line(const std::string& line) {
    return line.empty() || line[0] == ';' || line[0] == '#';
}

static void record_register_differences(const std::map<std::string, uint64_t>& initial,
                                        const std::map<std::string, uint64_t>& final_regs,
                                        std::map<std::string, std::pair<uint64_t, uint64_t>>& changed) {

    for (const auto& [reg, final_val] : final_regs) {
        uint64_t initial_val = initial.at(reg);

        if (initial_val != final_val)
            changed[reg] = {initial_val, final_val};
    }
}

FragmentExecutor::FragmentExecutor(ExecutorConfig config)
: config_(std::move(config))
, segment_loader_(config_.binary_path)
, instruction_emulator_(emulator) {}

void FragmentExecutor::set_use_native(bool native) {
    config_.use_native_execution = native;
}

void FragmentExecutor::set_binary_path(const std::string& path) {
    config_.binary_path = path;
    segment_loader_.set_binary_path(path);
}

uint64_t FragmentExecutor::get_register(const std::string& reg) const {
    return emulator.get(reg);
}

void FragmentExecutor::set_input(const std::string& reg, uint64_t value) {
    emulator.set(reg, value);
}

void FragmentExecutor::set_inputs(const std::map<std::string, uint64_t>& inputs) {
    for (const auto& [reg, val] : inputs)
        emulator.set(reg, val);
}

void FragmentExecutor::apply_memory_bytes(uint64_t address, const std::vector<uint8_t>& bytes) {
    emulator.write_bytes(address, bytes);
    record_native_memory(address, bytes);
}

void FragmentExecutor::apply_memory_patches(const std::vector<MemoryPatch>& patches) {
    for (const auto& patch : patches) {
        emulator.write_bytes(patch.address, patch.after);
        record_native_memory(patch.address, patch.after);
    }
}

void FragmentExecutor::preload_native_chunk(uint64_t address, const std::vector<uint8_t>& bytes) {
    record_native_memory(address, bytes);
}

void FragmentExecutor::record_native_memory(uint64_t address, const std::vector<uint8_t>& bytes) {
    if (bytes.empty())
        return;
    native_memory_chunks_[address] = bytes;
}

ExecutionResult FragmentExecutor::execute_safe(const std::string& asm_file) {
    ExecutionResult result;
    PatchLogGuard patch_guard(emulator, result.memory_patches);

    std::ifstream file(asm_file);
    if (!file) {
        result.error_message = "Impossible d'ouvrir " + asm_file;
        return result;
    }

    result.initial_regs = emulator.regs64;

    log::section("Exécution sécurisée (émulation)");
    log::info("Fichier: " + asm_file);

    for (std::string line; std::getline(file, line); ) {
        if (should_skip_line(line))
            continue;
        if (!emulate_instruction(line, result)) {
            result.error_message = "Erreur lors de l'émulation: " + line;
            return result;
        }
        result.instructions_executed++;
    }

    result.final_regs = emulator.regs64;
    record_register_differences(result.initial_regs, result.final_regs, result.changed_regs);

    result.success = true;
    return result;
}

ExecutionResult FragmentExecutor::execute_native(const std::vector<uint8_t>& binary_code,
                                                 std::optional<uint64_t> original_address) {
    ExecutionResult result;
    PatchLogGuard patch_guard(emulator, result.memory_patches);

    log::section("Exécution native (JIT)");
    log::warning("Cette opération peut être dangereuse.");

#ifdef __linux__
    const size_t minimal_size = binary_code.empty() ? 1 : binary_code.size();
    std::optional<NativeLayout> layout;

    if (original_address.has_value() && !native_memory_chunks_.empty())
        layout = compute_native_layout(*original_address, minimal_size, native_memory_chunks_);

    size_t allocation_size = layout
        ? align_up(layout->span, kNativeAlignment)
        : minimal_size;
    if (!allocation_size)
        allocation_size = minimal_size;

    uint8_t* base_ptr = nullptr;
    uint8_t* entry_ptr = nullptr;
    void* mapping_addr = nullptr;
    size_t mapping_size = 0;

    if (layout.has_value()) {
        const uint64_t page_base = layout->base & ~(static_cast<uint64_t>(kNativeAlignment) - 1);
        const size_t offset = static_cast<size_t>(layout->base - page_base);
        const size_t span_with_offset = layout->span + offset;
        const size_t fixed_size = align_up(span_with_offset, kNativeAlignment);
        void* desired = reinterpret_cast<void*>(page_base);
        void* fixed = mmap(desired,
                           fixed_size,
                           PROT_READ | PROT_WRITE | PROT_EXEC,
                           MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
                           -1,
                           0);
        if (fixed != MAP_FAILED) {
            mapping_addr = fixed;
            mapping_size = fixed_size;
            base_ptr = static_cast<uint8_t*>(fixed) + offset;
            entry_ptr = base_ptr;
        }
    }

    if (!base_ptr) {
        mapping_addr = mmap(nullptr,
                            allocation_size,
                            PROT_READ | PROT_WRITE | PROT_EXEC,
                            MAP_PRIVATE | MAP_ANONYMOUS,
                            -1,
                            0);

        if (mapping_addr == MAP_FAILED) {
            result.error_message = "Impossible d'allouer mémoire exécutable";
            return result;
        }

        mapping_size = allocation_size;
        base_ptr = static_cast<uint8_t*>(mapping_addr);
        entry_ptr = base_ptr;
    }

    if (layout.has_value()) {
        for (const auto& [addr, bytes] : native_memory_chunks_)
            copy_into_layout(base_ptr, allocation_size, layout->base, addr, bytes);
        copy_into_layout(base_ptr,
                         allocation_size,
                         layout->base,
                         *original_address,
                         binary_code);
        const size_t offset = static_cast<size_t>(*original_address - layout->base);
        entry_ptr = base_ptr + offset;
    } else if (!binary_code.empty())
        std::memcpy(base_ptr, binary_code.data(), binary_code.size());

    result.initial_regs = emulator.regs64;

    try {
        void (*func)() = reinterpret_cast<void (*)()>(entry_ptr);
        result.program_stdout = capture_program_stdout([&]() { func(); });
        result.success = true;
    } catch (...) {
        result.error_message = "Crash pendant l'exécution native";
    }

    if (mapping_addr)
        munmap(mapping_addr, mapping_size);
#else
    (void)binary_code;
    (void)original_address;
    result.error_message = "Exécution native non supportée sur cette plateforme";
#endif

    return result;
}

void FragmentExecutor::print_register_state() const {
    emulator.print_state();
}

std::string FragmentExecutor::capture_program_stdout(const std::function<void()>& func) {
    if (!config_.capture_stdout) {
        func();
        return "";
    }
#ifdef __linux__
    int pipefd[2];
    if (pipe(pipefd) == -1) {
        func();
        return "";
    }

    int old_stdout = dup(STDOUT_FILENO);
    if (old_stdout == -1) {
        close(pipefd[0]);
        close(pipefd[1]);
        func();
        return "";
    }

    fflush(stdout);
    if (dup2(pipefd[1], STDOUT_FILENO) == -1) {
        close(pipefd[0]);
        close(pipefd[1]);
        close(old_stdout);
        func();
        return "";
    }
    close(pipefd[1]);

    std::string output;
    try {
        func();
    } catch (...) {
        fflush(stdout);
        dup2(old_stdout, STDOUT_FILENO);
        close(old_stdout);
        close(pipefd[0]);
        throw;
    }

    fflush(stdout);
    dup2(old_stdout, STDOUT_FILENO);
    close(old_stdout);

    char buffer[256];
    ssize_t n;
    while ((n = read(pipefd[0], buffer, sizeof(buffer))) > 0)
        output.append(buffer, n);
    close(pipefd[0]);
    return output;
#else
    func();
    return "";
#endif
}

std::optional<std::string> FragmentExecutor::read_string_from_binary(uint64_t address) const {
    return segment_loader_.read_string(address);
}

bool FragmentExecutor::emulate_instruction(const std::string& line, ExecutionResult& result) {
    size_t colon_pos = line.find(':');
    if (colon_pos == std::string::npos)
        return true;

    std::string instruction = line.substr(colon_pos + 1);
    std::istringstream iss(instruction);
    std::string opcode;
    iss >> opcode;

    Opcode op = classify_opcode(opcode);
    if (op == Opcode::Call)
        return emulate_call(iss, result);

    return instruction_emulator_.emulate_line(line, result);
}

bool FragmentExecutor::emulate_call(std::istringstream& iss, ExecutionResult& result) {
    std::string target;
    std::getline(iss, target);
    target = fragment::trim(target);
    if (target.empty()) {
        iss.clear();
        iss >> target;
        target = fragment::trim(target);
    }
    if (target.empty())
        return true;

    if (target.find("puts") != std::string::npos) {
        uint64_t addr = emulator.get("rdi");
        auto text = read_string_from_binary(addr);
        if (text && !text->empty()) {
            result.program_stdout += *text;
            result.program_stdout.push_back('\n');
        }
        emulator.set("rax", text ? text->size() : 0);
        return true;
    }

    if (target.find("printf") != std::string::npos) {
        uint64_t addr = emulator.get("rdi");
        auto format = read_string_from_binary(addr);
        if (format)
            result.program_stdout += *format;
        return true;
    }

    return true;
}

}  // namespace fragment
