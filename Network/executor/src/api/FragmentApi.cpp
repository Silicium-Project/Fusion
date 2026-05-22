#include "api/FragmentApi.h"

#include <algorithm>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "api/FragmentApiResultAdapter.hpp"
#include "backend/ExecutionBackend.hpp"
#include "core/FragmentExecutor.hpp"
#include "partition/PartitionRegistry.hpp"
#include "partition/PartitionSummary.hpp"

using fragment::ExecutionEntry;
using fragment::ExecutionResult;
using fragment::FragmentExecutor;
using fragment::PartitionInfo;
using fragment::PartitionSummary;
using fragment::api::fill_result_from_execution;
using fragment::api::free_result_buffers;

namespace {

struct Context {
    fragment::ExecutorConfig config{};
};

class ScopedPartitionRegistry {
public:
    explicit ScopedPartitionRegistry(const std::vector<PartitionInfo>& partitions) {
        fragment::global_partition_registry().set(&partitions);
    }

    ~ScopedPartitionRegistry() {
        fragment::global_partition_registry().reset();
    }
};

std::map<std::string, uint64_t> to_registers(const FE_RegisterKV* entries, size_t count) {
    std::map<std::string, uint64_t> registers;
    for (size_t index = 0; index < count; ++index) {
        if (!entries[index].name)
            continue;
        registers[entries[index].name] = entries[index].value;
    }
    return registers;
}

std::vector<fragment::MemoryRegion> to_memory_regions(const FE_MemoryPage* pages, size_t count) {
    std::vector<fragment::MemoryRegion> regions;
    regions.reserve(count);
    for (size_t index = 0; index < count; ++index) {
        fragment::MemoryRegion region;
        region.address = pages[index].address;
        if (pages[index].data && pages[index].size)
            region.bytes.assign(pages[index].data, pages[index].data + pages[index].size);
        regions.push_back(std::move(region));
    }
    return regions;
}

std::vector<fragment::FdRule> to_fd_redirections(const FE_FdRedirection* fds, size_t count) {
    std::vector<fragment::FdRule> redirections;
    redirections.reserve(count);
    for (size_t index = 0; index < count; ++index) {
        fragment::FdRule redirection;
        redirection.fd = fds[index].fd;
        if (fds[index].input_data && fds[index].input_size)
            redirection.input_data.assign(reinterpret_cast<const char*>(fds[index].input_data), fds[index].input_size);
        redirection.capture = (fds[index].capture != 0);
        if (fds[index].alias)
            redirection.alias = fds[index].alias;
        redirections.push_back(std::move(redirection));
    }
    return redirections;
}

}  // namespace

extern "C" {

FE_Context* fe_create(void) {
    try {
        auto context = std::make_unique<Context>();
        return reinterpret_cast<FE_Context*>(context.release());
    } catch (...) {
        return nullptr;
    }
}

void fe_destroy(FE_Context* ctx) {
    std::unique_ptr<Context> context(reinterpret_cast<Context*>(ctx));
}

int fe_run(FE_Context* ctx, const FE_Task* task, FE_Result* out) {
    if (!ctx || !task || !out || !task->summary_path || !task->partition_id)
        return -1;

    auto& context = *reinterpret_cast<Context*>(ctx);
    PartitionSummary summary;
    try {
        summary = fragment::load_partition_summary(task->summary_path, false);
    } catch (...) {
        return -2;
    }

    auto partition_it = std::find_if(summary.partitions.begin(),
                                     summary.partitions.end(),
                                     [&](const PartitionInfo& partition) { return partition.id == task->partition_id; });
    if (partition_it == summary.partitions.end())
        return -3;

    std::string binary_override;
    if (task->binary_path && *task->binary_path)
        binary_override = task->binary_path;

    context.config.fd_rules = to_fd_redirections(task->fd_redirections, task->fd_redirections_count);

    FragmentExecutor executor(context.config);
    if (!binary_override.empty())
        executor.set_binary_path(binary_override);
    else if (!summary.binary_path.empty())
        executor.set_binary_path(summary.binary_path);

    ScopedPartitionRegistry scoped_partition_registry(summary.partitions);

    for (const auto& region : summary.initial_memory)
        executor.apply_memory_bytes(region.address, region.bytes);

    auto extra_memory = to_memory_regions(task->memory_pages, task->memory_page_count);
    for (const auto& region : extra_memory)
        executor.apply_memory_bytes(region.address, region.bytes);

    auto register_state = to_registers(task->register_state, task->register_state_count);
    for (const auto& [name, value] : register_state)
        executor.set_input(name, value);

    auto inputs = to_registers(task->inputs, task->input_count);
    executor.set_inputs(inputs);

    ExecutionEntry entry;
    entry.name = partition_it->id;
    entry.asm_path = partition_it->asm_path;
    entry.meta = std::cref(*partition_it);

    ExecutionResult result;
    auto backend = fragment::make_backend(task->native_mode != 0, task->force_native != 0);
    bool run_ok = false;
    try {
        run_ok = backend->run(entry, executor, result);
    } catch (...) {
        return -4;
    }
    if (!run_ok)
        return -4;

    if (!fill_result_from_execution(result, out))
        return -5;
    return 0;
}

void fe_free_result(FE_Result* out) {
    free_result_buffers(out);
}

}  // extern "C"
