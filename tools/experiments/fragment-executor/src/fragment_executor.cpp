#include "fragment/fragment_executor.hpp"

#ifdef __linux__
#include <sys/mman.h>
#include <unistd.h>
#endif

#include "fragment/logging.hpp"
#include "fragment/utils.hpp"

namespace fragment {

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
}

void FragmentExecutor::apply_memory_patches(const std::vector<MemoryPatch>& patches) {
    for (const auto& patch : patches)
        emulator.write_bytes(patch.address, patch.after);
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

ExecutionResult FragmentExecutor::execute_native(const std::vector<uint8_t>& binary_code) {
    ExecutionResult result;
    PatchLogGuard patch_guard(emulator, result.memory_patches);

    log::section("Exécution native (JIT)");
    log::warning("Cette opération peut être dangereuse.");

#ifdef __linux__
    void* exec_mem = mmap(nullptr,
                          binary_code.size(),
                          PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_PRIVATE | MAP_ANONYMOUS,
                          -1,
                          0);

    if (exec_mem == MAP_FAILED) {
        result.error_message = "Impossible d'allouer mémoire exécutable";
        return result;
    }

    std::memcpy(exec_mem, binary_code.data(), binary_code.size());
    result.initial_regs = emulator.regs64;

    try {
        void (*func)() = reinterpret_cast<void (*)()>(exec_mem);
        result.program_stdout = capture_program_stdout([&]() { func(); });
        result.success = true;
    } catch (...) {
        result.error_message = "Crash pendant l'exécution native";
    }

    munmap(exec_mem, binary_code.size());
#else
    (void)binary_code;
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
