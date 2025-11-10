#include "splitter/instruction_analysis.hpp"

#include <regex>
#include <set>
#include <sstream>

#include "splitter/util.hpp"

namespace splitter {

namespace {

const std::set<std::string> kJumpOpcodes = {
    "jmp", "je", "jne", "jg", "jge", "jl", "jle",
    "ja", "jae", "jb", "jbe", "jz", "jnz", "js",
    "jns", "jo", "jno", "jp", "jnp"
};

const std::set<std::string> kCallOpcodes = {"call", "callq"};

const std::set<std::string> kRegisters = {
    "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rsp", "rbp",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
    "eax", "ebx", "ecx", "edx", "esi", "edi", "esp", "ebp",
    "al", "ah", "bl", "bh", "cl", "ch", "dl", "dh", "sil", "dil",
    "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5", "xmm6", "xmm7"
};

const std::set<std::string> kStackOps = {"push", "pop", "call", "ret"};

}  // namespace

void analyze_instruction(AsmInstruction& inst) {
    if (kJumpOpcodes.count(inst.opcode)) {
        inst.is_jump = true;
        std::regex target_regex("0x([0-9a-f]+)");
        std::smatch match;
        if (std::regex_search(inst.operands, match, target_regex))
            inst.target_addr = std::stoull(match[1].str(), nullptr, 16);
    }

    if (kCallOpcodes.count(inst.opcode)) {
        inst.is_call = true;
        std::regex target_regex("0x([0-9a-f]+)");
        std::smatch match;
        if (std::regex_search(inst.operands, match, target_regex))
            inst.target_addr = std::stoull(match[1].str(), nullptr, 16);
    }

    std::vector<std::string> ops;
    std::stringstream ss(inst.operands);
    std::string op;
    while (std::getline(ss, op, ',')) {
        ops.push_back(trim(op));
    }

    for (const auto& operand : ops) {
        const bool memory_op = operand.find('[') != std::string::npos ||
                               operand.find("PTR") != std::string::npos;
        if (memory_op)
            inst.is_memory = true;
        for (const auto& reg : kRegisters) {
            if (operand.find(reg) != std::string::npos) {
                inst.reads.insert(reg);
                break;
            }
        }
    }

    if (!ops.empty() && inst.opcode != "cmp" && inst.opcode != "test" && inst.opcode != "push") {
        const auto& dest = ops[0];
        if (dest.find('[') != std::string::npos || dest.find("PTR") != std::string::npos)
            inst.is_memory = true;
        else
            for (const auto& reg : kRegisters) {
                if (dest.find(reg) != std::string::npos) {
                    inst.writes.insert(reg);
                    break;
                }
            }
    }

    if (kStackOps.count(inst.opcode)) {
        inst.reads.insert("rsp");
        inst.writes.insert("rsp");
    }

    if (inst.opcode == "call")
        for (const auto& reg : {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"})
            inst.writes.insert(reg);
}

bool analyze_function_loops(Function& func) {
    for (const auto& inst : func.instructions) {
        if (inst.is_jump && inst.target_addr.has_value() && inst.target_addr.value() <= inst.address) {
            func.is_loop = true;
            return true;
        }
    }
    return false;
}

std::map<std::string, std::string> detect_loop_patterns(const Function& func) {
    std::map<std::string, std::string> result;
    if (!func.is_loop) {
        result["parallelizable"] = "false";
        result["reason"] = "pas de boucle";
        return result;
    }

    bool has_memory = false;
    for (const auto& inst : func.instructions) {
        if (inst.is_memory) {
            has_memory = true;
            break;
        }
    }

    result["parallelizable"] = has_memory ? "false" : "true";
    result["reason"] = has_memory ? "memory dependencies" : "no memory writes";
    return result;
}

}  // namespace splitter
