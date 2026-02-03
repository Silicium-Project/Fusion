#include "core/FragmentExecutor.hpp"

#ifdef __linux__
#include <sys/mman.h>
#include <ucontext.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#endif

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>

#include "support/Logging.hpp"
#include "support/Utils.hpp"

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

static std::optional<uint64_t> parse_address(const std::string& line) {
    auto pos = line.find(':');
    if (pos == std::string::npos || pos == 0)
        return std::nullopt;
    try {
        return std::stoull(line.substr(0, pos), nullptr, 16);
    } catch (...) {
        return std::nullopt;
    }
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

    // Précharger toutes les lignes avec leur adresse (si présente).
    struct LineInfo {
        std::optional<uint64_t> addr;
        std::string text;
    };
    std::vector<LineInfo> lines;
    for (std::string line; std::getline(file, line); ) {
        lines.push_back({parse_address(line), line});
    }

    result.initial_regs = emulator.regs64;

    log::section("Exécution sécurisée (émulation)");
    log::info("Fichier: " + asm_file);

    for (size_t idx = 0; idx < lines.size(); ++idx) {
        const auto& info = lines[idx];
        if (should_skip_line(info.text))
            continue;
        std::optional<uint64_t> next_addr;
        if (idx + 1 < lines.size())
            next_addr = lines[idx + 1].addr;
        instruction_emulator_.set_next_instruction_address(next_addr);
        if (!emulate_instruction(info.text, result)) {
            result.error_message = "Erreur lors de l'émulation: " + info.text;
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

    // Rien à exécuter : considérer la partition comme un no-op.
    if (binary_code.empty()) {
        result.initial_regs = emulator.regs64;
        result.final_regs = emulator.regs64;
        result.success = true;
        return result;
    }

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
        if (binary_code.empty() && offset < allocation_size)
            base_ptr[offset] = 0xC3;  // ret
    } else {
        if (!binary_code.empty())
            std::memcpy(base_ptr, binary_code.data(), binary_code.size());
        else
            base_ptr[0] = 0xC3;  // ret
    }

    result.initial_regs = emulator.regs64;

    const size_t stack_size = std::max<std::size_t>(config_.emulated_stack_size, 64 * 1024);
    void* native_stack =
            mmap(nullptr, stack_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (!native_stack || native_stack == MAP_FAILED) {
        if (mapping_addr)
            munmap(mapping_addr, mapping_size);
        result.error_message = "Impossible d'allouer une pile native";
        return result;
    }

    auto cleanup = [&]() {
        munmap(native_stack, stack_size);
        if (mapping_addr)
            munmap(mapping_addr, mapping_size);
    };

    try {
        auto pipes = capture_program_pipes([&]() {
            using Fn = void (*)();
            Fn func = reinterpret_cast<Fn>(entry_ptr);
            ucontext_t caller {};
            ucontext_t ctx {};
            if (getcontext(&ctx) == -1)
                throw std::runtime_error("getcontext a échoué");
            ctx.uc_stack.ss_sp = native_stack;
            ctx.uc_stack.ss_size = stack_size;
            ctx.uc_link = &caller;
            makecontext(&ctx, func, 0);
            if (swapcontext(&caller, &ctx) == -1)
                throw std::runtime_error("swapcontext a échoué");
        });
        result.fd_outputs = std::move(pipes.fds);
        if (result.fd_outputs.contains(STDOUT_FILENO))
            result.program_stdout = result.fd_outputs.at(STDOUT_FILENO).data;
        if (result.fd_outputs.contains(STDERR_FILENO))
            result.program_stderr = result.fd_outputs.at(STDERR_FILENO).data;
        result.success = true;
    } catch (const std::exception& ex) {
        result.error_message = ex.what();
    } catch (...) {
        result.error_message = "Exécution native a échoué";
    }

    result.final_regs = emulator.regs64;
    cleanup();
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

FragmentExecutor::PipeCaptures FragmentExecutor::capture_program_pipes(const std::function<void()>& func) {
#ifdef __linux__
    std::vector<FdRule> rules = config_.fd_rules;
    if (rules.empty()) {
        rules.push_back(FdRule{STDIN_FILENO, {}, false, "stdin"});
        rules.push_back(FdRule{STDOUT_FILENO, {}, true, "stdout"});
        rules.push_back(FdRule{STDERR_FILENO, {}, true, "stderr"});
    }

    struct SigpipeGuard {
        struct sigaction oldact {};
        SigpipeGuard() {
            struct sigaction act {};
            act.sa_handler = SIG_IGN;
            sigemptyset(&act.sa_mask);
            act.sa_flags = 0;
            sigaction(SIGPIPE, &act, &oldact);
        }
        ~SigpipeGuard() {
            sigaction(SIGPIPE, &oldact, nullptr);
        }
    } guard;

    PipeCaptures captures;

    struct PipeSet {
        int fd = -1;
        int read_end = -1;
        int write_end = -1;
        std::string input;
        bool capture = false;
        std::string alias;
    };

    std::vector<PipeSet> pipes;
    pipes.reserve(rules.size());

    for (const auto& rule : rules) {
        if (rule.fd < 0)
            continue;
        PipeSet p;
        p.fd = rule.fd;
        p.input = rule.input_data;
        p.capture = rule.capture && rule.input_data.empty();
        p.alias = rule.alias;
        pipes.push_back(std::move(p));
    }

    std::map<int, int> saved_fds;

    auto safe_close = [](int fd) {
        if (fd != -1)
            close(fd);
    };

    auto read_pipe = [](int fd, std::string& dest) {
        if (fd == -1)
            return;
        int flags = fcntl(fd, F_GETFL, 0);
        if (flags != -1)
            fcntl(fd, F_SETFL, flags | O_NONBLOCK);
        char buffer[256];
        ssize_t n;
        while ((n = read(fd, buffer, sizeof(buffer))) > 0)
            dest.append(buffer, n);
    };

    for (auto& p : pipes) {
        int fds[2]{-1, -1};
        if (pipe(fds) == -1) {
            fds[0] = fds[1] = -1;
        }
        auto bump_fd = [](int fd) {
            if (fd == -1)
                return fd;
            int duped = fcntl(fd, F_DUPFD_CLOEXEC, 64);
            close(fd);
            return duped;
        };
        p.read_end = bump_fd(fds[0]);
        p.write_end = bump_fd(fds[1]);

        int old = dup(p.fd);
        if (old != -1)
            saved_fds[p.fd] = old;

        fflush(stdout);
        fflush(stderr);

        if (!p.input.empty()) {
            if (p.read_end == -1)
                continue;
            dup2(p.read_end, p.fd);
            safe_close(p.read_end);
            p.read_end = -1;
        } else {
            if (p.write_end == -1)
                continue;
            dup2(p.write_end, p.fd);
            safe_close(p.write_end);
            p.write_end = -1;
        }
    }

    for (auto& p : pipes) {
        if (p.input.empty() || p.write_end == -1)
            continue;
        const uint8_t* ptr = reinterpret_cast<const uint8_t*>(p.input.data());
        size_t remaining = p.input.size();
        while (remaining > 0) {
            ssize_t w = write(p.write_end, ptr, remaining);
            if (w <= 0)
                break;
            ptr += w;
            remaining -= static_cast<size_t>(w);
        }
        safe_close(p.write_end);
        p.write_end = -1;
    }

    try {
        func();
    } catch (...) {
        fflush(stdout);
        fflush(stderr);
        for (const auto& [fd, old] : saved_fds) {
            dup2(old, fd);
            safe_close(old);
        }
        for (auto& p : pipes) {
            safe_close(p.read_end);
            safe_close(p.write_end);
        }
        throw;
    }

    fflush(stdout);
    fflush(stderr);

    for (const auto& [fd, old] : saved_fds) {
        dup2(old, fd);
        safe_close(old);
    }

    for (auto& p : pipes)
        safe_close(p.write_end);

    for (auto& p : pipes) {
        if (p.capture) {
            std::string data;
            read_pipe(p.read_end, data);
            FdCapture cap;
            cap.data = std::move(data);
            cap.alias = p.alias;
            captures.fds.set(p.fd, std::move(cap));
        }
        safe_close(p.read_end);
    }

    return captures;
#else
    func();
    return {};
#endif
}

std::string FragmentExecutor::capture_program_stdout(const std::function<void()>& func) {
    auto res = capture_program_pipes(func);
    if (res.fds.contains(STDOUT_FILENO))
        return res.fds.at(STDOUT_FILENO).data;
    return {};
}

std::optional<std::string> FragmentExecutor::read_string_from_binary(uint64_t address) const {
    return segment_loader_.read_string(address);
}

namespace {

struct CallArgs {
    uint64_t fmt = 0;
    std::array<uint64_t, 5> regs{};  // rsi, rdx, rcx, r8, r9 (printf ordre SysV)
};

CallArgs gather_call_args(const RegisterEmulator& emulator) {
    CallArgs args{};
    args.fmt = emulator.get("rdi");
    args.regs[0] = emulator.get("rsi");
    args.regs[1] = emulator.get("rdx");
    args.regs[2] = emulator.get("rcx");
    args.regs[3] = emulator.get("r8");
    args.regs[4] = emulator.get("r9");
    return args;
}

std::string format_printf_like(const std::string& fmt, const CallArgs& args) {
    std::ostringstream out;
    size_t arg_idx = 0;
    for (size_t i = 0; i < fmt.size(); ++i) {
        char c = fmt[i];
        if (c != '%') {
            out << c;
            continue;
        }
        if (i + 1 < fmt.size() && fmt[i + 1] == '%') {
            out << '%';
            ++i;
            continue;
        }

        // Parse flags/width (minimal subset)
        size_t j = i + 1;
        int width = 0;
        while (j < fmt.size() && std::isdigit(static_cast<unsigned char>(fmt[j]))) {
            width = width * 10 + (fmt[j] - '0');
            ++j;
        }
        bool is_long = false;
        bool is_long_long = false;
        if (j + 1 < fmt.size() && fmt[j] == 'l' && fmt[j + 1] == 'l') {
            is_long_long = true;
            j += 2;
        } else if (j < fmt.size() && fmt[j] == 'l') {
            is_long = true;
            ++j;
        }
        if (j >= fmt.size())
            break;

        char spec = fmt[j];
        if (arg_idx >= args.regs.size()) {
            out << '%' << spec;
            i = j;
            continue;
        }
        uint64_t val = args.regs[arg_idx++];
        std::ostringstream val_ss;
        if (spec == 'x' || spec == 'X') {
            val_ss << std::hex << std::nouppercase;
            if (width > 0)
                val_ss << std::setw(width) << std::setfill('0');
            val_ss << val;
        } else if (spec == 'u' || spec == 'd') {
            if (width > 0)
                val_ss << std::setw(width) << std::setfill('0');
            if (spec == 'd')
                val_ss << static_cast<long long>(val);
            else
                val_ss << static_cast<unsigned long long>(val);
        } else if (spec == 'p') {
            val_ss << "0x" << std::hex << val;
        } else if (spec == 's') {
            // For %s assume rsi (first arg) is a pointer; best effort.
            (void)is_long;
            (void)is_long_long;
            // Not implemented fully; fallback to raw pointer.
            val_ss << "0x" << std::hex << val;
        } else {
            out << '%' << spec;
            i = j;
            continue;
        }
        out << val_ss.str();
        i = j;
    }
    return out.str();
}

bool is_printf_symbol(const std::string& target) {
    return target.find("printf") != std::string::npos || target.find("__printf_chk") != std::string::npos;
}

}  // namespace

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
        if (!text) {
            // fallback: tente de charger en mémoire émulée et relit
            if (auto buf = segment_loader_.read_bytes(addr, 64); !buf.empty()) {
                emulator.write_bytes(addr, buf);
                text = read_string_from_binary(addr);
            }
        }
        if (text && !text->empty()) {
            result.program_stdout += *text;
            result.program_stdout.push_back('\n');
        }
        emulator.set("rax", text ? text->size() : 0);
        return true;
    }

    if (is_printf_symbol(target)) {
        const auto args = gather_call_args(emulator);
        auto format = read_string_from_binary(args.fmt);
        if (format)
            result.program_stdout += format_printf_like(*format, args);
        return true;
    }

    return true;
}

}  // namespace fragment
