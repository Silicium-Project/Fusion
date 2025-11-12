#include "fragment/instruction_emulator.hpp"

#include "fragment/config.hpp"
#include "fragment/utils.hpp"

namespace fragment {

InstructionEmulator::InstructionEmulator(RegisterEmulator& emulator)
: emulator_(emulator) {}

bool InstructionEmulator::emulate_line(const std::string& line, ExecutionResult& result) {
    size_t colon = line.find(':');
    if (colon == std::string::npos)
        return true;

    std::string instruction = line.substr(colon + 1);
    std::istringstream iss(instruction);
    std::string opcode;
    iss >> opcode;

    const Opcode op = classify_opcode(opcode);
    switch (op) {
        case Opcode::Mov:
            return emulate_mov(iss, result);
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

bool InstructionEmulator::emulate_mov(std::istringstream& iss, ExecutionResult& result) {
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

    if (src.empty())
        return true;

    uint64_t value = 0;
    if (src.front() == '$' || std::isdigit(static_cast<unsigned char>(src.front())))
        value = parse_immediate(src);
    else if (src.front() == '[')
        result.memory_accesses++;
    else
        value = emulator_.get(src);

    emulator_.set(dest, value);
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
    emulator_.ZF = (computed == 0);
    emulator_.SF = (computed & (1ULL << 63)) != 0;
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
    emulator_.ZF = (result_val == 0);
    emulator_.SF = (result_val & (1ULL << 63)) != 0;
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

    uint64_t rsp = emulator_.get(FRAGMENT_STACK_POINTER);
    rsp -= 8;
    emulator_.set(FRAGMENT_STACK_POINTER, rsp);

    uint64_t value = emulator_.get(src);
    emulator_.write_qword(rsp, value);
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
    if (s.size() > 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X'))
        return std::stoull(s, nullptr, 16);
    return std::stoull(s);
}

std::string InstructionEmulator::trim(const std::string& token) const {
    size_t begin = token.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos)
        return "";
    size_t end = token.find_last_not_of(" \t\r\n");
    return token.substr(begin, end - begin + 1);
}

}  // namespace fragment
