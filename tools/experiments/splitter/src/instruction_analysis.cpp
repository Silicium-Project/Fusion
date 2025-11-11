#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

#include <algorithm>
#include <array>
#include <regex>
#include <sstream>
#include <string_view>
#include <vector>

namespace splitter {

    template <typename Container>
    static bool contains(std::string_view opcode, const Container& list) {
        return std::find(list.begin(), list.end(), opcode) != list.end();
    }

    static constexpr std::array<std::string_view, 19> kJumpOpcodes = {
        "jmp", "je",  "jne", "jg",  "jge", "jl",  "jle",
        "ja",  "jae", "jb",  "jbe", "jz",  "jnz", "js",
        "jns", "jo",  "jno", "jp",  "jnp"
    };

    static constexpr std::array<std::string_view, 42> kRegisters = {
        "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rsp", "rbp",
        "r8",  "r9",  "r10", "r11", "r12", "r13", "r14", "r15",
        "eax", "ebx", "ecx", "edx", "esi", "edi", "esp", "ebp",
        "al",  "ah",  "bl",  "bh",  "cl",  "ch",  "dl",  "dh",
        "sil", "dil", "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5",
        "xmm6", "xmm7"
    };

    static constexpr std::array<std::string_view, 2> kCallOpcodes = {"call", "callq"};

    static constexpr std::array<std::string_view, 4> kStackOpcodes = {"push", "pop", "call", "ret"};

    static constexpr std::array<std::string_view, 7> kCallClobberedRegisters = {
        "rax", "rcx", "rdx", "r8", "r9", "r10", "r11"
    };

    bool is_jump_opcode(std::string_view opcode) {
        return contains(opcode, kJumpOpcodes);
    }

    bool is_call_opcode(std::string_view opcode) {
        return contains(opcode, kCallOpcodes);
    }

    bool is_stack_opcode(std::string_view opcode) {
        return contains(opcode, kStackOpcodes);
    }

    bool is_call_clobbered_reg(std::string_view reg) {
        return contains(reg, kCallClobberedRegisters);
    }

    static bool is_memory_operand(const std::string& operand) {
        return operand.find('[') != std::string::npos
            || operand.find("PTR") != std::string::npos;
    }

    static void record_register_reads(const std::string& operand, AsmInstruction& inst) {
        for (const auto& reg : kRegisters)
            if (operand.find(reg) != std::string::npos) {
                inst.reads.insert(std::string(reg));
                break;
            }
    }

    static void mark_destination_write(const std::vector<std::string>& ops, AsmInstruction& inst) {
        if (ops.empty())
            return;
        if (inst.opcode == "cmp"
         || inst.opcode == "test"
         || inst.opcode == "push")
            return;

        const std::string& dest = ops.front();

        if (is_memory_operand(dest)) {
            inst.is_memory = true;
            return;
        }

        for (const auto& reg : kRegisters)
            if (dest.find(reg) != std::string::npos) {
                inst.writes.insert(std::string(reg));
                break;
            }
    }

    static void mark_control_flow(AsmInstruction& inst, bool is_jump) {
        std::regex pattern("0x([0-9a-f]+)");
        std::smatch match;

        if (!std::regex_search(inst.operands, match, pattern))
            return;

        inst.target_addr = std::stoull(match[1].str(), nullptr, 16);

        if (is_jump)
            inst.is_jump = true;
        else
            inst.is_call = true;
    }

    static void parse_operands(const std::string& operands, AsmInstruction& inst) {
        std::vector<std::string> ops;
        std::stringstream ss(operands);
        std::string raw;

        while (std::getline(ss, raw, ','))
            ops.push_back(trim(raw));

        for (const auto& operand : ops) {
            if (is_memory_operand(operand))
                inst.is_memory = true;
            record_register_reads(operand, inst);
        }

        mark_destination_write(ops, inst);
    }

    static void mark_stack_effect(AsmInstruction& inst) {
        if (!is_stack_opcode(inst.opcode))
            return;

        inst.reads.insert("rsp");
        inst.writes.insert("rsp");
    }

    static void mark_call_clobbers(AsmInstruction& inst) {
        if (inst.opcode != "call")
            return;

        for (const auto& reg : kRegisters)
            if (is_call_clobbered_reg(reg))
                inst.writes.insert(std::string(reg));
    }

    void analyze_instruction(AsmInstruction& inst) {
        if (is_jump_opcode(inst.opcode))
            mark_control_flow(inst, true);

        if (is_call_opcode(inst.opcode))
            mark_control_flow(inst, false);

        parse_operands(inst.operands, inst);
        mark_stack_effect(inst);
        mark_call_clobbers(inst);
    }

    bool analyze_function_loops(Function& func) {
        for (const auto& inst : func.instructions)
            if (inst.is_jump && inst.target_addr.has_value()
            && inst.target_addr.value() <= inst.address) {
                func.is_loop = true;
                return true;
            }

        return false;
    }

    std::map<std::string, std::string> detect_loop_patterns(const Function& func) {
        bool has_memory = false;

        if (!func.is_loop)
            return std::map<std::string, std::string>({
                {"parallelizable", "false"},
                {"reason", "pas de boucle"}
            });

        for (const auto& inst : func.instructions)
            if (inst.is_memory) {
                has_memory = true;
                break;
            }

        return std::map<std::string, std::string>({
            {"parallelizable", has_memory ? "false" : "true"},
            {"reason", has_memory ? "memory dependencies" : "no memory writes"}
        });
    }

}  // namespace splitter
