#include "worker/backend/ExecutorClient.hpp"

#include <dlfcn.h>

#include <cstring>
#include <stdexcept>
#include <utility>
#include <vector>

#include "partition/PartitionSummary.hpp"
#include "worker/backend/BackendRequest.hpp"

namespace worker {

template <typename Map>
static std::vector<FE_RegisterKV> to_kv(const Map& regs, std::vector<std::string>& storage) {
    std::vector<FE_RegisterKV> out;
    out.reserve(regs.size());
    storage.reserve(storage.size() + regs.size());
    for (const auto& [name, value] : regs) {
        storage.push_back(name);
        out.push_back(FE_RegisterKV{storage.back().c_str(), value});
    }
    return out;
}

static fragment::ExecutionResult to_execution_result(const FE_Result& res) {
    fragment::ExecutionResult out;
    out.success = res.success != 0;
    if (res.error_message)
        out.error_message = res.error_message;
    out.instructions_executed = res.instructions_executed;
    out.memory_accesses = res.memory_accesses;
    if (res.program_stdout)
        out.program_stdout = res.program_stdout;
    if (res.program_stderr)
        out.program_stderr = res.program_stderr;
    if (res.fd_outputs && res.fd_outputs_count) {
        for (size_t i = 0; i < res.fd_outputs_count; ++i) {
            const auto& fd_out = res.fd_outputs[i];
            if (fd_out.fd < 0)
                continue;
            fragment::FdCapture cap;
            if (fd_out.data && fd_out.size)
                cap.data.assign(reinterpret_cast<const char*>(fd_out.data), fd_out.size);
            if (fd_out.alias)
                cap.alias = fd_out.alias;
            out.fd_outputs[fd_out.fd] = std::move(cap);
        }
    }

    for (size_t i = 0; i < res.changed_registers_count; ++i) {
        const auto& reg = res.changed_registers[i];
        if (!reg.name)
            continue;
        out.changed_regs[reg.name] = {reg.before, reg.after};
        out.initial_regs[reg.name] = reg.before;
        out.final_regs[reg.name] = reg.after;
    }

    for (size_t i = 0; i < res.memory_patches_count; ++i) {
        const auto& patch_in = res.memory_patches[i];
        fragment::MemoryPatch patch;
        patch.address = patch_in.address;
        if (patch_in.before && patch_in.before_size)
            patch.before.assign(patch_in.before, patch_in.before + patch_in.before_size);
        if (patch_in.after && patch_in.after_size)
            patch.after.assign(patch_in.after, patch_in.after + patch_in.after_size);
        out.memory_patches.push_back(std::move(patch));
    }
    return out;
}


ExecutorClient::ExecutorClient(std::string library_path) {
    handle_ = std::unique_ptr<void, DllCloser>(
        dlopen(library_path.c_str(), RTLD_NOW),
        [](void* handle) {
            if (handle)
                dlclose(handle);
        });
    if (!handle_)
        throw std::runtime_error("Impossible de charger la bibliothèque: " + library_path);

    auto load_sym = [&](const char* name) -> void* {
        void* sym = dlsym(handle_.get(), name);
        if (!sym)
            throw std::runtime_error(std::string("Symbole manquant dans la bibliothèque: ") + name);
        return sym;
    };

    auto create = reinterpret_cast<CreateFn>(load_sym("fe_create"));
    auto destroy = reinterpret_cast<DestroyFn>(load_sym("fe_destroy"));
    run_ = reinterpret_cast<RunFn>(load_sym("fe_run"));
    free_result_ = reinterpret_cast<FreeResultFn>(load_sym("fe_free_result"));

    ContextDeleter deleter = [destroy](FE_Context* ctx) {
        if (destroy && ctx)
            destroy(ctx);
    };
    context_ = std::unique_ptr<FE_Context, ContextDeleter>(create(), std::move(deleter));
    if (!context_)
        throw std::runtime_error("Impossible d'initialiser le contexte d'exécution");
}

fragment::ExecutionResult ExecutorClient::run(const BackendRequest& request,
                                              bool native_mode,
                                              bool force_native) const {
    if (!run_ || !free_result_)
        throw std::runtime_error("API d'exécution invalide (pointeurs nuls)");
    if (request.summary_path.empty())
        throw std::runtime_error("Chemin du summary manquant pour le backend d'exécution");

    FE_Task task{};
    task.summary_path = request.summary_path.c_str();
    task.partition_id = request.partition.id.c_str();
    task.binary_path = request.binary_path.empty() ? nullptr : request.binary_path.c_str();
    task.native_mode = native_mode ? 1 : 0;
    task.force_native = force_native ? 1 : 0;

    std::vector<std::string> input_names;
    std::vector<std::string> state_names;
    auto inputs_kv = to_kv(request.inputs, input_names);
    auto state_kv = to_kv(request.register_state, state_names);
    task.inputs = inputs_kv.data();
    task.input_count = inputs_kv.size();
    task.register_state = state_kv.data();
    task.register_state_count = state_kv.size();

    std::vector<FE_MemoryPage> pages;
    pages.reserve(request.memory_state.size());
    for (const auto& snapshot : request.memory_state) {
        FE_MemoryPage page{};
        page.address = snapshot.address;
        page.data = snapshot.bytes.data();
        page.size = snapshot.bytes.size();
        pages.push_back(page);
    }
    task.memory_pages = pages.data();
    task.memory_page_count = pages.size();

    std::vector<FE_FdRedirection> fd_redirs;
    fd_redirs.reserve(request.fd_rules.size());
    std::vector<std::vector<uint8_t>> fd_inputs_storage;
    std::vector<std::string> fd_alias_storage;
    fd_inputs_storage.reserve(request.fd_rules.size());
    fd_alias_storage.reserve(request.fd_rules.size());
    for (const auto& redir : request.fd_rules) {
        FE_FdRedirection c_fd{};
        c_fd.fd = redir.fd;
        c_fd.capture = redir.capture ? 1 : 0;
        if (!redir.input_data.empty()) {
            fd_inputs_storage.emplace_back(redir.input_data.begin(), redir.input_data.end());
            c_fd.input_data = fd_inputs_storage.back().data();
            c_fd.input_size = fd_inputs_storage.back().size();
        }
        if (!redir.alias.empty()) {
            fd_alias_storage.push_back(redir.alias);
            c_fd.alias = fd_alias_storage.back().c_str();
        } else {
            c_fd.alias = nullptr;
        }
        fd_redirs.push_back(c_fd);
    }
    task.fd_redirections = fd_redirs.data();
    task.fd_redirections_count = fd_redirs.size();

    FE_Result c_result{};
    const int code = run_(context_.get(), &task, &c_result);
    fragment::ExecutionResult result;
    if (code == 0) {
        result = to_execution_result(c_result);
    } else {
        result.success = false;
        result.error_message = "Erreur backend (" + std::to_string(code) + ")";
    }
    free_result_(&c_result);
    return result;
}

}  // namespace worker
