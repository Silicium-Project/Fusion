#pragma once

#include "core/Common.hpp"
#include "core/ExecutionResult.hpp"
#include "core/Memory.hpp"
#include "core/Opcodes.hpp"

namespace fragment {

class InstructionEmulator {
public:
    explicit InstructionEmulator(RegisterEmulator& emulator);

    bool emulate_line(const std::string& line, ExecutionResult& result);
    void set_next_instruction_address(std::optional<uint64_t> addr);
    void preload_bytes(uint64_t address, const std::vector<uint8_t>& bytes);

    private:
        RegisterEmulator& emulator_;
        std::optional<uint64_t> next_insn_addr_;
        std::optional<uint64_t> current_insn_addr_;

        bool emulate_mov(std::istringstream& iss, ExecutionResult& result);
        bool emulate_lea(std::istringstream& iss, ExecutionResult& result);
        bool emulate_binary_op(std::istringstream& iss, ExecutionResult& result, Opcode opcode);
        bool emulate_xor(std::istringstream& iss, ExecutionResult& result);
        bool emulate_inc(std::istringstream& iss);
        bool emulate_dec(std::istringstream& iss);
        bool emulate_push(std::istringstream& iss, ExecutionResult& result);
        bool emulate_pop(std::istringstream& iss, ExecutionResult& result);

        uint64_t parse_immediate(const std::string& token) const;
        std::string trim(const std::string& token) const;
        size_t register_width(const std::string& reg) const;
        size_t infer_memory_width(const std::string& operand, size_t fallback) const;
        std::optional<uint64_t> resolve_memory_address(const std::string& operand) const;
        std::optional<uint64_t> read_memory_value(uint64_t address, size_t width) const;
        void write_memory_value(uint64_t address, uint64_t value, size_t width);
        std::optional<uint64_t> evaluate_operand(const std::string& operand,
                                                 size_t width_hint,
                                                 ExecutionResult& result);
    };

}  // namespace fragment
