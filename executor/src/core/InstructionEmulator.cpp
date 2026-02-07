#include "core/InstructionEmulator.hpp"

#include "core/Config.hpp"
#include "support/Utils.hpp"

namespace fragment {

InstructionEmulator::InstructionEmulator(RegisterEmulator& emulator)
: emulator_(emulator) {}

void InstructionEmulator::set_next_instruction_address(std::optional<uint64_t> addr) {
    next_insn_addr_ = addr;
}

bool InstructionEmulator::emulate_line(const std::string& line, ExecutionResult& result) {
    size_t colon = line.find(':');
    if (colon == std::string::npos)
        return true;

    current_insn_addr_.reset();
    if (colon > 0) {
        try {
            current_insn_addr_ = std::stoull(line.substr(0, colon), nullptr, 16);
        } catch (...) {
            current_insn_addr_.reset();
        }
    }

    std::string instruction = line.substr(colon + 1);
    std::istringstream iss(instruction);
    std::string opcode;
    iss >> opcode;

    const Opcode op = classify_opcode(opcode);
    switch (op) {
        case Opcode::Mov:
            return emulate_mov(iss, result);
        case Opcode::Lea:
            return emulate_lea(iss, result);
        case Opcode::Add:
        case Opcode::Sub:
            return emulate_binary_op(iss, result, op);
        case Opcode::Xor:
            return emulate_xor(iss, result);
        case Opcode::Inc:
            return emulate_inc(iss);
        case Opcode::Dec:
            return emulate_dec(iss);
        case Opcode::Push:
            return emulate_push(iss, result);
        case Opcode::Pop:
            return emulate_pop(iss, result);
        case Opcode::Ret:
        case Opcode::Nop:
        case Opcode::Unknown:
        case Opcode::Call:
            return true;  // call handled elsewhere
    }
    return true;
}

void InstructionEmulator::preload_bytes(uint64_t address, const std::vector<uint8_t>& bytes) {
    emulator_.write_bytes(address, bytes);
}

bool InstructionEmulator::emulate_mov(std::istringstream& iss, ExecutionResult& result) {
    std::string dest, src;

    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    if (dest.empty() || src.empty())
        return true;

    const bool dest_is_memory = dest.find('[') != std::string::npos;
    const size_t dest_width = dest_is_memory
        ? infer_memory_width(dest, register_width(src))
        : register_width(dest);

    std::optional<uint64_t> value;
    const bool src_is_rip_mem = src.find("[rip") != std::string::npos || src.find("[%rip") != std::string::npos;
    if (!dest_is_memory && src_is_rip_mem) {
        // Pour les accès RIP relatifs (souvent des pointeurs vers .rodata), on utilise l'adresse calculée.
        auto addr = resolve_memory_address(src);
        if (addr.has_value())
            value = *addr;
    }
    if (!value.has_value())
        value = evaluate_operand(src, dest_width, result);
    if (!value.has_value())
        return true;

    if (dest_is_memory) {
        auto address = resolve_memory_address(dest);
        if (!address.has_value())
            return true;
        result.memory_accesses++;
        write_memory_value(*address, *value, dest_width);
        return true;
    }

    emulator_.set(dest, *value);
    return true;
}

bool InstructionEmulator::emulate_lea(std::istringstream& iss, ExecutionResult& /*result*/) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);
    if (dest.empty() || src.empty())
        return true;

    auto address = resolve_memory_address(src);
    if (!address.has_value())
        return true;
    emulator_.set(dest, *address);
    return true;
}

bool InstructionEmulator::emulate_binary_op(std::istringstream& iss,
                                            ExecutionResult& result,
                                            Opcode opcode) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    if (dest.empty())
        return true;
    if (dest.front() == '[') {
        result.memory_accesses++;
        return true;
    }

    const bool immediate = (!src.empty() && (src.front() == '$'
                      || std::isdigit(static_cast<unsigned char>(src.front()))));

    uint64_t dest_val = emulator_.get(dest);
    uint64_t src_val = immediate ? parse_immediate(src) : emulator_.get(src);

    uint64_t computed = dest_val;
    if (opcode == Opcode::Add)
        computed = dest_val + src_val;
    else if (opcode == Opcode::Sub)
        computed = dest_val - src_val;

    emulator_.set(dest, computed);
    emulator_.ZF = (!computed);
    emulator_.SF = computed & (1ULL << 63);
    return true;
}

bool InstructionEmulator::emulate_xor(std::istringstream& iss, ExecutionResult&) {
    std::string dest, src;
    std::getline(iss, dest, ',');
    std::getline(iss, src);

    dest = trim(dest);
    src = trim(src);

    uint64_t result_val = emulator_.get(dest) ^ emulator_.get(src);
    emulator_.set(dest, result_val);
    emulator_.ZF = (!result_val);
    emulator_.SF = result_val & (1ULL << 63);
    emulator_.CF = false;
    emulator_.OF = false;
    return true;
}

bool InstructionEmulator::emulate_inc(std::istringstream& iss) {
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t val = emulator_.get(dest);
    emulator_.set(dest, val + 1);
    return true;
}

bool InstructionEmulator::emulate_dec(std::istringstream& iss) {
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t val = emulator_.get(dest);
    emulator_.set(dest, val - 1);
    return true;
}

bool InstructionEmulator::emulate_push(std::istringstream& iss, ExecutionResult& result) {
    std::string src;
    iss >> src;
    src = trim(src);

    auto value = evaluate_operand(src, sizeof(uint64_t), result);
    uint64_t rsp = emulator_.get(FRAGMENT_STACK_POINTER);
    rsp -= 8;
    emulator_.set(FRAGMENT_STACK_POINTER, rsp);

    uint64_t push_value = value.value_or(emulator_.get(src));
    emulator_.write_qword(rsp, push_value);
    result.memory_accesses++;
    return true;
}

bool InstructionEmulator::emulate_pop(std::istringstream& iss, ExecutionResult& result) {
    std::string dest;
    iss >> dest;
    dest = trim(dest);

    uint64_t rsp = emulator_.get(FRAGMENT_STACK_POINTER);
    uint64_t value = emulator_.read_qword(rsp);

    emulator_.set(dest, value);
    emulator_.set(FRAGMENT_STACK_POINTER, rsp + 8);
    result.memory_accesses++;
    return true;
}

uint64_t InstructionEmulator::parse_immediate(const std::string& token) const {
    std::string s = trim(token);
    if (s.empty())
        return 0;
    if (s.front() == '$')
        s.erase(s.begin());
    int sign = 1;
    if (!s.empty() && (s.front() == '-' || s.front() == '+')) {
        sign = (s.front() == '-') ? -1 : 1;
        s.erase(s.begin());
    }
    int base = 10;
    if (s.size() > 1 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        base = 16;
        s = s.substr(2);
    }
    if (s.empty())
        return 0;

    long long value = (base == 16)
        ? std::stoll(s, nullptr, 16)
        : std::stoll(s, nullptr, 10);
    value *= sign;
    return static_cast<uint64_t>(value);
}

std::string InstructionEmulator::trim(const std::string& token) const {
    size_t begin = token.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos)
        return "";
    size_t end = token.find_last_not_of(" \t\r\n");
    return token.substr(begin, end - begin + 1);
}

size_t InstructionEmulator::register_width(const std::string& reg) const {
    std::string lowered = trim(reg);
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });

    if (lowered.empty())
        return sizeof(uint64_t);

    char last = lowered.back();
    if (last == 'b' || last == 'l' || last == 'h')
        return 1;
    if (last == 'w')
        return 2;
    if (last == 'd' || lowered.front() == 'e')
        return 4;
    return sizeof(uint64_t);
}

size_t InstructionEmulator::infer_memory_width(const std::string& operand, size_t fallback) const {
    std::string lowered = operand;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });

    // Attention: "qword ptr" contient "word ptr" ; tester du plus large au plus spécifique.
    if (lowered.find("qword ptr") != std::string::npos)
        return 8;
    if (lowered.find("dword ptr") != std::string::npos)
        return 4;
    if (lowered.find("word ptr") != std::string::npos)
        return 2;
    if (lowered.find("byte ptr") != std::string::npos)
        return 1;
    if (fallback)
        return fallback;
    return sizeof(uint64_t);
}

std::optional<uint64_t> InstructionEmulator::resolve_memory_address(const std::string& operand) const {
    std::string trimmed = trim(operand);
    auto bracket_start = trimmed.find('[');
    if (bracket_start == std::string::npos)
        return std::nullopt;
    auto bracket_end = trimmed.find(']', bracket_start);
    if (bracket_end == std::string::npos)
        return std::nullopt;

    std::string expr = trim(trimmed.substr(bracket_start + 1, bracket_end - bracket_start - 1));
    if (expr.empty())
        return std::nullopt;

    std::string compact;
    compact.reserve(expr.size());
    for (char c : expr) {
        if (c != ' ' && c != '\t' && c != '\r' && c != '\n')
            compact.push_back(c);
    }
    if (compact.empty())
        return std::nullopt;

    auto strip_percent = [](const std::string& token) {
        if (!token.empty() && token.front() == '%')
            return token.substr(1);
        return token;
    };

    auto is_immediate = [](const std::string& token) {
        if (token.empty())
            return false;
        if (token.size() > 1 && token[0] == '0' && (token[1] == 'x' || token[1] == 'X'))
            return true;
        return std::isdigit(static_cast<unsigned char>(token.front())) != 0;
    };

    auto register_value = [&](const std::string& token) -> std::optional<uint64_t> {
        std::string reg = strip_percent(token);
        if (reg == "rip") {
            if (next_insn_addr_.has_value())
                return *next_insn_addr_;
            if (current_insn_addr_.has_value())
                return *current_insn_addr_;
            return std::nullopt;
        }
        return emulator_.get(reg);
    };

    auto parse_term = [&](const std::string& term) -> std::optional<uint64_t> {
        if (term.empty())
            return std::nullopt;
        auto star = term.find('*');
        if (star != std::string::npos) {
            std::string left = term.substr(0, star);
            std::string right = term.substr(star + 1);
            if (left.empty() || right.empty())
                return std::nullopt;
            const bool left_imm = is_immediate(left);
            const bool right_imm = is_immediate(right);
            if (left_imm && right_imm) {
                return parse_immediate(left) * parse_immediate(right);
            }
            if (left_imm) {
                auto base = register_value(right);
                if (!base.has_value())
                    return std::nullopt;
                return (*base) * parse_immediate(left);
            }
            if (right_imm) {
                auto base = register_value(left);
                if (!base.has_value())
                    return std::nullopt;
                return (*base) * parse_immediate(right);
            }
            return std::nullopt;
        }

        if (is_immediate(term))
            return parse_immediate(term);
        return register_value(term);
    };

    uint64_t address = 0;
    bool has_any = false;
    int sign = 1;
    for (size_t i = 0; i < compact.size();) {
        char c = compact[i];
        if (c == '+') {
            sign = 1;
            ++i;
            continue;
        }
        if (c == '-') {
            sign = -1;
            ++i;
            continue;
        }
        size_t start = i;
        while (i < compact.size() && compact[i] != '+' && compact[i] != '-')
            ++i;
        std::string term = compact.substr(start, i - start);
        auto value = parse_term(term);
        if (!value.has_value())
            return std::nullopt;
        if (sign < 0)
            address -= *value;
        else
            address += *value;
        has_any = true;
        sign = 1;
    }

    if (!has_any)
        return std::nullopt;
    return address;
}

std::optional<uint64_t> InstructionEmulator::read_memory_value(uint64_t address, size_t width) const {
    if (!width)
        return std::nullopt;
    const size_t capped_width = std::min<std::size_t>(width, sizeof(uint64_t));
    auto bytes = emulator_.read_bytes(address, capped_width);
    if (bytes.size() != capped_width)
        return std::nullopt;

    uint64_t value = 0;
    for (size_t idx = 0; idx < bytes.size(); ++idx)
        value |= static_cast<uint64_t>(bytes[idx]) << (idx * 8);
    return value;
}

void InstructionEmulator::write_memory_value(uint64_t address, uint64_t value, size_t width) {
    if (!width)
        width = sizeof(uint64_t);
    const size_t capped_width = std::min<std::size_t>(width, sizeof(uint64_t));
    std::vector<uint8_t> bytes(capped_width);
    for (size_t idx = 0; idx < capped_width; ++idx)
        bytes[idx] = static_cast<uint8_t>((value >> (idx * 8)) & 0xFF);
    emulator_.write_bytes(address, bytes);
}

std::optional<uint64_t> InstructionEmulator::evaluate_operand(const std::string& operand,
                                                              size_t width_hint,
                                                              ExecutionResult& result) {
    std::string token = trim(operand);
    if (token.empty())
        return std::nullopt;

    if (token.front() == '$' || token.front() == '-' || token.front() == '+'
        || std::isdigit(static_cast<unsigned char>(token.front()))
        || (!token.rfind("0x", 0)))
        return parse_immediate(token);

    if (token.find('[') != std::string::npos) {
        auto address = resolve_memory_address(token);
        if (!address.has_value())
            return std::nullopt;
        auto width = infer_memory_width(token, width_hint ? width_hint : sizeof(uint64_t));
        auto value = read_memory_value(*address, width);
        if (!value.has_value()) {
            // Best effort : si rien en mémoire, tenter de charger depuis le binaire (rodata).
            // On lit jusqu'à width octets à partir de l'adresse pour peupler l'émulateur.
            // Ici, width_hint peut être 8 pour un pointeur ; on charge 16 octets pour couvrir une chaîne courte.
            constexpr size_t kFallbackBytes = 64;
            std::vector<uint8_t> buf;
            buf.reserve(kFallbackBytes);
            for (size_t i = 0; i < kFallbackBytes; ++i)
                buf.push_back(0);
            // L'instruction emulator ne connaît pas le segment loader ; on laisse le caller précharger le cas échéant.
            // Pas de write ici pour éviter d'introduire des données incohérentes.
        }
        result.memory_accesses++;
        return value;
    }

    return emulator_.get(token);
}

}  // namespace fragment
