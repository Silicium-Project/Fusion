#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <optional>
#include <regex>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include "splitter/architecture.hpp"
#include "splitter/types.hpp"

namespace splitter {

    enum class OpcodeId : std::uint8_t {
        Cmp,
        Test,
        Push,
        Pop,
        Call,
        Callq,
        Ret,
        Jump,
        Other
    };

    struct LoopAnalysis {
        bool parallelizable = false;
        std::string reason;
    };

    struct ParsedOperand;

    OpcodeId classify_opcode(std::string_view opcode);

    class InstructionAnalyzer {
    public:
        static InstructionAnalyzer& instance();

        void analyze_instruction(AsmInstruction& inst) const;
        bool analyze_function_loops(Function& func) const;
        LoopAnalysis detect_loop_patterns(const Function& func) const;

    private:
        InstructionAnalyzer() = default;

        void record_register_reads(const ParsedOperand& operand, AsmInstruction& inst) const;
        void mark_destination_write(const ParsedOperand& dest, OpcodeId opcode_id, AsmInstruction& inst) const;
        void mark_control_flow(AsmInstruction& inst, bool is_jump) const;
        void parse_operands(const std::string& operands, OpcodeId opcode_id, AsmInstruction& inst) const;
        void mark_stack_effect(AsmInstruction& inst, OpcodeId opcode_id) const;
        void mark_call_clobbers(AsmInstruction& inst, OpcodeId opcode_id) const;
        bool should_skip_destination(OpcodeId opcode_id) const;
    };

    bool is_jump_opcode(std::string_view opcode);
    bool is_call_opcode(std::string_view opcode);
    bool is_stack_opcode(std::string_view opcode);
    bool is_call_clobbered_reg(std::string_view reg);

    void analyze_instruction(AsmInstruction& inst);
    bool analyze_function_loops(Function& func);
    LoopAnalysis detect_loop_patterns(const Function& func);

}  // namespace splitter
