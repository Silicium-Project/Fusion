#include "api/FragmentApi.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "cli/Cli.hpp"
#include "core/FragmentExecutor.hpp"
#include "partition/PartitionRegistry.hpp"
#include "partition/PartitionSummary.hpp"
#include "backend/ExecutionBackend.hpp"

using fragment::ExecutionEntry;
using fragment::ExecutionResult;
using fragment::FragmentExecutor;
using fragment::PartitionInfo;
using fragment::PartitionSummary;

namespace {

struct Context {
    fragment::ExecutorConfig config{};
};

std::map<std::string, uint64_t> to_registers(const FE_RegisterKV* entries, size_t count) {
    std::map<std::string, uint64_t> regs;
    for (size_t i = 0; i < count; ++i) {
        if (!entries[i].name) continue;
        regs[entries[i].name] = entries[i].value;
    }
    return regs;
}

std::vector<fragment::MemoryRegion> to_memory_regions(const FE_MemoryPage* pages, size_t count) {
    std::vector<fragment::MemoryRegion> regions;
    regions.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        fragment::MemoryRegion region;
        region.address = pages[i].address;
        if (pages[i].data && pages[i].size)
            region.bytes.assign(pages[i].data, pages[i].data + pages[i].size);
        regions.push_back(std::move(region));
    }
    return regions;
}

std::vector<fragment::FdRule> to_fd_redirections(const FE_FdRedirection* fds, size_t count) {
    std::vector<fragment::FdRule> out;
    out.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        fragment::FdRule redir;
        redir.fd = fds[i].fd;
        if (fds[i].input_data && fds[i].input_size)
            redir.input_data.assign(reinterpret_cast<const char*>(fds[i].input_data), fds[i].input_size);
        redir.capture = (fds[i].capture != 0);
        if (fds[i].alias)
            redir.alias = fds[i].alias;
        out.push_back(std::move(redir));
    }
    return out;
}

void fill_result(const ExecutionResult& in, FE_Result* out) {
    out->success = in.success ? 1 : 0;
    out->error_message = nullptr;
    if (!in.error_message.empty()) {
        char* buffer = static_cast<char*>(std::malloc(in.error_message.size() + 1));
        if (buffer) {
            std::memcpy(buffer, in.error_message.data(), in.error_message.size());
            buffer[in.error_message.size()] = '\0';
            out->error_message = buffer;
        }
    }
    out->instructions_executed = in.instructions_executed;
    out->memory_accesses = in.memory_accesses;

    out->program_stdout = nullptr;
    if (!in.program_stdout.empty()) {
        out->program_stdout = static_cast<char*>(std::malloc(in.program_stdout.size() + 1));
        std::memcpy(out->program_stdout, in.program_stdout.data(), in.program_stdout.size());
        out->program_stdout[in.program_stdout.size()] = '\0';
    }
    out->program_stderr = nullptr;
    if (!in.program_stderr.empty()) {
        out->program_stderr = static_cast<char*>(std::malloc(in.program_stderr.size() + 1));
        std::memcpy(out->program_stderr, in.program_stderr.data(), in.program_stderr.size());
        out->program_stderr[in.program_stderr.size()] = '\0';
    }

    out->fd_outputs_count = in.fd_outputs.size();
    out->fd_outputs = static_cast<FE_FdOutput*>(std::calloc(out->fd_outputs_count, sizeof(FE_FdOutput)));
    size_t fd_idx = 0;
    for (const auto& [fd, cap] : in.fd_outputs.entries()) {
        out->fd_outputs[fd_idx].fd = fd;
        out->fd_outputs[fd_idx].size = cap.data.size();
        if (!cap.alias.empty()) {
            out->fd_outputs[fd_idx].alias = static_cast<char*>(std::malloc(cap.alias.size() + 1));
            if (out->fd_outputs[fd_idx].alias) {
                std::memcpy(out->fd_outputs[fd_idx].alias, cap.alias.data(), cap.alias.size());
                out->fd_outputs[fd_idx].alias[cap.alias.size()] = '\0';
            }
        } else {
            out->fd_outputs[fd_idx].alias = nullptr;
        }
        if (!cap.data.empty()) {
            out->fd_outputs[fd_idx].data = static_cast<uint8_t*>(std::malloc(cap.data.size()));
            std::memcpy(out->fd_outputs[fd_idx].data, cap.data.data(), cap.data.size());
        }
        ++fd_idx;
    }

    out->changed_registers_count = in.changed_regs.size();
    out->changed_registers = static_cast<FE_ChangedRegister*>(
        std::calloc(out->changed_registers_count, sizeof(FE_ChangedRegister)));
    size_t idx = 0;
    for (const auto& [name, values] : in.changed_regs) {
        char* name_copy = static_cast<char*>(std::malloc(name.size() + 1));
        if (name_copy) {
            std::memcpy(name_copy, name.data(), name.size());
            name_copy[name.size()] = '\0';
        }
        out->changed_registers[idx].name = name_copy;
        out->changed_registers[idx].before = values.first;
        out->changed_registers[idx].after = values.second;
        ++idx;
    }

    out->memory_patches_count = in.memory_patches.size();
    out->memory_patches = static_cast<FE_MemoryPatchOut*>(
        std::calloc(out->memory_patches_count, sizeof(FE_MemoryPatchOut)));
    for (size_t i = 0; i < in.memory_patches.size(); ++i) {
        const auto& patch = in.memory_patches[i];
        out->memory_patches[i].address = patch.address;
        out->memory_patches[i].before_size = patch.before.size();
        out->memory_patches[i].after_size = patch.after.size();
        if (!patch.before.empty()) {
            out->memory_patches[i].before = static_cast<uint8_t*>(std::malloc(patch.before.size()));
            std::memcpy(out->memory_patches[i].before, patch.before.data(), patch.before.size());
        }
        if (!patch.after.empty()) {
            out->memory_patches[i].after = static_cast<uint8_t*>(std::malloc(patch.after.size()));
            std::memcpy(out->memory_patches[i].after, patch.after.data(), patch.after.size());
        }
    }
}

}  // namespace

extern "C" {

FE_Context* fe_create(void) {
    try {
        return reinterpret_cast<FE_Context*>(new Context{});
    } catch (...) {
        return nullptr;
    }
}

void fe_destroy(FE_Context* ctx) {
    delete reinterpret_cast<Context*>(ctx);
}

int fe_run(FE_Context* ctx, const FE_Task* task, FE_Result* out) {
    if (!ctx || !task || !out || !task->summary_path || !task->partition_id)
        return -1;

    auto* context = reinterpret_cast<Context*>(ctx);
    PartitionSummary summary;
    try {
        summary = fragment::load_partition_summary(task->summary_path, false);
    } catch (...) {
        return -2;
    }

    auto it = std::find_if(summary.partitions.begin(),
                           summary.partitions.end(),
                           [&](const PartitionInfo& p) { return p.id == task->partition_id; });
    if (it == summary.partitions.end())
        return -3;

    std::string binary_override;
    if (task->binary_path && *task->binary_path)
        binary_override = task->binary_path;

    context->config.fd_rules = to_fd_redirections(task->fd_redirections, task->fd_redirections_count);

    FragmentExecutor executor(context->config);
    if (!binary_override.empty())
        executor.set_binary_path(binary_override);
    else if (!summary.binary_path.empty())
        executor.set_binary_path(summary.binary_path);

    fragment::set_partition_registry(&summary.partitions);

    for (const auto& region : summary.initial_memory)
        executor.apply_memory_bytes(region.address, region.bytes);

    auto extra_mem = to_memory_regions(task->memory_pages, task->memory_page_count);
    for (const auto& region : extra_mem)
        executor.apply_memory_bytes(region.address, region.bytes);

    auto reg_state = to_registers(task->register_state, task->register_state_count);
    for (const auto& [reg, val] : reg_state)
        executor.set_input(reg, val);

    auto inputs = to_registers(task->inputs, task->input_count);
    executor.set_inputs(inputs);

    ExecutionEntry entry;
    entry.name = it->id;
    entry.asm_path = it->asm_path;
    entry.meta = std::cref(*it);

    ExecutionResult result;
    auto backend = fragment::make_backend(task->native_mode != 0, task->force_native != 0);
    bool ok = backend->run(entry, executor, result);
    fragment::set_partition_registry(nullptr);
    if (!ok)
        return -4;

    fill_result(result, out);
    return 0;
}

void fe_free_result(FE_Result* out) {
    if (!out)
        return;
    if (out->program_stdout)
        std::free(out->program_stdout);
    if (out->fd_outputs) {
        for (size_t i = 0; i < out->fd_outputs_count; ++i) {
            std::free(out->fd_outputs[i].data);
            std::free(out->fd_outputs[i].alias);
        }
        std::free(out->fd_outputs);
    }
    if (out->program_stderr)
        std::free(out->program_stderr);
    if (out->changed_registers) {
        for (size_t i = 0; i < out->changed_registers_count; ++i)
            std::free(const_cast<char*>(out->changed_registers[i].name));
        std::free(out->changed_registers);
    }
    if (out->memory_patches) {
        for (size_t i = 0; i < out->memory_patches_count; ++i) {
            std::free(out->memory_patches[i].before);
            std::free(out->memory_patches[i].after);
        }
        std::free(out->memory_patches);
    }
    if (out->error_message)
        std::free(const_cast<char*>(out->error_message));
    std::memset(out, 0, sizeof(*out));
}

}  // extern "C"
