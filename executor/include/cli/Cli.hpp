#pragma once

#include "core/Common.hpp"
#include "core/FragmentExecutor.hpp"
#include "partition/PartitionSummary.hpp"

namespace fragment {

struct ExecutionEntry {
    std::string name;
    std::string asm_path;
    std::optional<std::reference_wrapper<const PartitionInfo>> meta;
};

struct CliOptions {
    std::vector<std::string> asm_files;
    std::map<std::string, uint64_t> inputs;
    bool native_mode = false;
    bool force_native = false;
    bool skip_memory_check = false;
    std::string summary_file;
    std::string log_path;
};

void print_usage(std::string_view prog);
CliOptions parse_arguments(const std::vector<std::string_view>& args);
bool open_log_file(const std::string& path, std::ofstream& stream);
void apply_inputs(FragmentExecutor& executor, const std::map<std::string, uint64_t>& inputs);

std::vector<ExecutionEntry> plan_from_summary(const std::vector<PartitionInfo>& partitions,
                                              std::set<std::string>& expected_inputs);

std::vector<ExecutionEntry> plan_from_files(const std::vector<std::string>& asm_files);

void print_plan_overview(const std::string& summary_file, const std::vector<ExecutionEntry>& plan);

void describe_entry(size_t idx, const ExecutionEntry& entry);

bool prepare_external_inputs(const ExecutionEntry& entry,
                             FragmentExecutor& executor,
                             const std::map<std::string, uint64_t>& inputs,
                             std::set<std::string>& consumed_inputs);

std::string derive_binary_path(const ExecutionEntry& entry);

bool execute_entry(const ExecutionEntry& entry,
                   bool native_mode,
                   bool force_native,
                   FragmentExecutor& executor,
                   ExecutionResult& result);

void log_program_output(std::ofstream& log_stream, const ExecutionResult& result);

void warn_unused_inputs(const std::set<std::string>& expected,
                        const std::set<std::string>& consumed,
                        const std::map<std::string, uint64_t>& inputs);

void set_partition_registry(const std::vector<PartitionInfo>* partitions);

}  // namespace fragment
