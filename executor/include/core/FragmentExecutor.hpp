#pragma once

#include "core/Common.hpp"
#include "core/Config.hpp"
#include "core/ExecutionResult.hpp"
#include "core/Memory.hpp"

#include "core/Opcodes.hpp"
#include "core/InstructionEmulator.hpp"
#include "core/SegmentLoader.hpp"
#include "partition/PartitionSummary.hpp"

namespace fragment {

class FragmentExecutor {
public:
    explicit FragmentExecutor(ExecutorConfig config = {});

    void set_use_native(bool native);
    void set_binary_path(const std::string& path);
    uint64_t get_register(const std::string& reg) const;
    void set_input(const std::string& reg, uint64_t value);
    void set_inputs(const std::map<std::string, uint64_t>& inputs);
    void apply_memory_bytes(uint64_t address, const std::vector<uint8_t>& bytes);
    void apply_memory_patches(const std::vector<MemoryPatch>& patches);
    void preload_native_chunk(uint64_t address, const std::vector<uint8_t>& bytes);

    ExecutionResult execute_safe(const std::string& asm_file);
    ExecutionResult execute_native(const std::vector<uint8_t>& binary_code,
                                   std::optional<uint64_t> original_address = std::nullopt);
    void print_register_state() const;
    struct PipeCaptures {
        FdTable fds;
    };

    PipeCaptures capture_program_pipes(const std::function<void()>& func);
    std::string capture_program_stdout(const std::function<void()>& func);

private:
    RegisterEmulator emulator;
    ExecutorConfig config_;
    SegmentLoader segment_loader_;
    InstructionEmulator instruction_emulator_;
    std::map<uint64_t, std::vector<uint8_t>> native_memory_chunks_;

    bool emulate_instruction(const std::string& line, ExecutionResult& result);
    bool emulate_call(std::istringstream& iss, ExecutionResult& result);
    std::optional<std::string> read_string_from_binary(uint64_t address) const;
    void record_native_memory(uint64_t address, const std::vector<uint8_t>& bytes);
};

}  // namespace fragment
