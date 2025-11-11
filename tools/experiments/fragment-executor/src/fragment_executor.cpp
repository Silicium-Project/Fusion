#include "fragment/fragment_executor.hpp"

#include <algorithm>
#include <array>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <queue>
#include <set>

#ifdef __linux__
#include <sys/mman.h>
#include <unistd.h>
#endif

#include <elf.h>

#include "fragment/logging.hpp"
#include "fragment/utils.hpp"

namespace fragment {

static bool should_skip_line(const std::string& line) {
    return line.empty() || line[0] == ';' || line[0] == '#';
}

template <typename T>
static bool read_struct(std::ifstream& stream, T& value) {
    std::array<char, sizeof(T)> buffer{};

    if (!stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size())))
        return false;

    std::memcpy(&value, buffer.data(), buffer.size());
    return true;
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

FragmentExecutor::FragmentExecutor(bool native) : use_native_execution(native), segments_loaded(false) {}

void FragmentExecutor::set_use_native(bool native) {
    use_native_execution = native;
}

void FragmentExecutor::set_binary_path(const std::string& path) {
    binary_path = path;
    segments_loaded = false;
    segments.clear();
    string_cache.clear();
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

bool FragmentExecutor::ensure_segments_loaded() const {
    if (segments_loaded || binary_path.empty())
        return segments_loaded;

    std::ifstream bin(binary_path, std::ios::binary);
    if (!bin)
        return false;

    Elf64_Ehdr ehdr{};
    if (!read_struct(bin, ehdr) || std::memcmp(ehdr.e_ident, ELFMAG, SELFMAG) != 0
        || ehdr.e_ident[EI_CLASS] != ELFCLASS64)
        return false;

    bin.seekg(ehdr.e_phoff, std::ios::beg);
    segments.clear();
    for (uint16_t i = 0; i < ehdr.e_phnum; ++i) {
        Elf64_Phdr phdr{};
        if (!read_struct(bin, phdr)) {
            segments.clear();
            return false;
        }
        if (phdr.p_type == PT_LOAD && phdr.p_filesz > 0) {
            SegmentMapping seg;
            seg.vaddr = phdr.p_vaddr;
            seg.memsz = phdr.p_memsz;
            seg.offset = phdr.p_offset;
            segments.push_back(seg);
        }
    }

    segments_loaded = true;
    return true;
}

std::string FragmentExecutor::read_string_from_binary(uint64_t address) const {
    if (!ensure_segments_loaded())
        return "";

    auto cache_it = string_cache.find(address);
    if (cache_it != string_cache.end())
        return cache_it->second;

    for (const auto& seg : segments) {
        if (address >= seg.vaddr && address < seg.vaddr + seg.memsz) {
            uint64_t offset = seg.offset + (address - seg.vaddr);
            std::ifstream bin(binary_path, std::ios::binary);
            if (!bin)
                return "";
            bin.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
            if (!bin)
                return "";
            std::string result;
            result.reserve(64);
            char c;
            size_t count = 0;
            while (count < 512 && bin.get(c)) {
                if (c == '\0')
                    break;
                result.push_back(c);
                ++count;
            }
            string_cache[address] = result;
            return result;
        }
    }

    return "";
}

bool FragmentExecutor::emulate_instruction(const std::string& line, ExecutionResult& result) {
    size_t colon_pos = line.find(':');
    if (colon_pos == std::string::npos)
        return true;

    std::string instruction = line.substr(colon_pos + 1);
    std::istringstream iss(instruction);
    std::string opcode;
    iss >> opcode;

    if (opcode == "mov" || opcode == "movq" || opcode == "movl")
        return emulate_mov(iss, result);
    if (opcode == "add" || opcode == "addq" || opcode == "addl")
        return emulate_add(iss, result);
    if (opcode == "sub" || opcode == "subq" || opcode == "subl")
        return emulate_sub(iss, result);
    if (opcode == "xor" || opcode == "xorq" || opcode == "xorl")
        return emulate_xor(iss, result);
    if (opcode == "inc" || opcode == "incq" || opcode == "incl")
        return emulate_inc(iss, result);
    if (opcode == "dec" || opcode == "decq" || opcode == "decl")
        return emulate_dec(iss, result);
    if (opcode == "push" || opcode == "pushq")
        return emulate_push(iss, result);
    if (opcode == "pop" || opcode == "popq")
        return emulate_pop(iss, result);
    if (opcode == "call" || opcode == "callq")
        return emulate_call(iss, result);
    if (opcode == "ret" || opcode == "retq")
        return true;
    if (opcode == "nop")
        return true;

    return true;
}

bool FragmentExecutor::emulate_mov(std::istringstream& iss, ExecutionResult& result) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    if (dest.empty())
        return true;

    if (dest[0] == '[') {
        result.memory_accesses++;
        return true;
    }

    uint64_t value = 0;
    if (src.empty())
        return true;

    if (src[0] == '$' || (src[0] >= '0' && src[0] <= '9'))
        value = parse_immediate(src);
    else if (src[0] == '[')
        result.memory_accesses++;
    else
        value = emulator.get(src);

    emulator.set(dest, value);
    return true;
}

bool FragmentExecutor::emulate_add(std::istringstream& iss, ExecutionResult& result) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    if (dest[0] == '[') {
        result.memory_accesses++;
        return true;
    }

    uint64_t dest_val = emulator.get(dest);
    uint64_t src_val = (src[0] == '$' || (src[0] >= '0' && src[0] <= '9'))
                           ? parse_immediate(src)
                           : emulator.get(src);

    uint64_t result_val = dest_val + src_val;
    emulator.set(dest, result_val);
    emulator.ZF = (result_val == 0);
    emulator.SF = (result_val & (1ULL << 63)) != 0;

    return true;
}

bool FragmentExecutor::emulate_sub(std::istringstream& iss, ExecutionResult& result) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    if (dest[0] == '[') {
        result.memory_accesses++;
        return true;
    }

    uint64_t dest_val = emulator.get(dest);
    uint64_t src_val = (src[0] == '$' || (src[0] >= '0' && src[0] <= '9'))
                           ? parse_immediate(src)
                           : emulator.get(src);

    uint64_t result_val = dest_val - src_val;
    emulator.set(dest, result_val);

    emulator.ZF = (result_val == 0);
    emulator.SF = (result_val & (1ULL << 63)) != 0;

    return true;
}

bool FragmentExecutor::emulate_xor(std::istringstream& iss, ExecutionResult& result) {
    (void)result;
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    uint64_t dest_val = emulator.get(dest);
    uint64_t src_val = emulator.get(src);

    uint64_t result_val = dest_val ^ src_val;
    emulator.set(dest, result_val);

    emulator.ZF = (result_val == 0);
    emulator.SF = (result_val & (1ULL << 63)) != 0;
    emulator.CF = false;
    emulator.OF = false;

    return true;
}

bool FragmentExecutor::emulate_inc(std::istringstream& iss, ExecutionResult& result) {
    (void)result;
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t val = emulator.get(dest);
    emulator.set(dest, val + 1);

    return true;
}

bool FragmentExecutor::emulate_dec(std::istringstream& iss, ExecutionResult& result) {
    (void)result;
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t val = emulator.get(dest);
    emulator.set(dest, val - 1);

    return true;
}

bool FragmentExecutor::emulate_push(std::istringstream& iss, ExecutionResult& result) {
    std::string src;
    iss >> src;
    src = trim(src);

    uint64_t rsp = emulator.get("rsp");
    rsp -= 8;
    emulator.set("rsp", rsp);

    uint64_t value = emulator.get(src);
    emulator.write_qword(rsp, value);
    result.memory_accesses++;

    return true;
}

bool FragmentExecutor::emulate_pop(std::istringstream& iss, ExecutionResult& result) {
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t rsp = emulator.get("rsp");
    uint64_t value = 0;
    value = emulator.read_qword(rsp);

    emulator.set(dest, value);
    emulator.set("rsp", rsp + 8);
    result.memory_accesses++;

    return true;
}

bool FragmentExecutor::emulate_call(std::istringstream& iss, ExecutionResult& result) {
    std::string target;
    std::getline(iss, target);
    target = trim(target);
    if (target.empty()) {
        iss.clear();
        iss >> target;
    }
    if (target.empty())
        return true;

    if (target.find("puts") != std::string::npos) {
        uint64_t addr = emulator.get("rdi");
        std::string text = read_string_from_binary(addr);
        if (!text.empty()) {
            result.program_stdout += text;
            result.program_stdout.push_back('\n');
        }
        emulator.set("rax", text.empty() ? 0 : text.size());
        return true;
    }

    if (target.find("printf") != std::string::npos) {
        uint64_t addr = emulator.get("rdi");
        std::string format = read_string_from_binary(addr);
        if (!format.empty())
            result.program_stdout += format;
        return true;
    }

    return true;
}

uint64_t FragmentExecutor::parse_immediate(const std::string& str) const {
    std::string s = str;
    if (s[0] == '$')
        s = s.substr(1);

    if (s.size() > 2 && s.substr(0, 2) == "0x")
        return std::stoull(s, nullptr, 16);
    return std::stoull(s);
}

std::string FragmentExecutor::trim(const std::string& str) {
    return fragment::trim(str);
}

}  // namespace fragment
