#include "api/FragmentApiResultAdapter.hpp"

#include <cstring>
#include <memory>
#include <string_view>

namespace fragment::api {
namespace {

template <typename T>
std::unique_ptr<T[]> copy_bytes_to_buffer(const std::vector<T>& bytes) {
    if (bytes.empty())
        return {};
    auto buffer = std::make_unique<T[]>(bytes.size());
    std::memcpy(buffer.get(), bytes.data(), bytes.size() * sizeof(T));
    return buffer;
}

std::unique_ptr<uint8_t[]> copy_raw_bytes_to_buffer(const std::string& bytes) {
    if (bytes.empty())
        return {};
    auto buffer = std::make_unique<uint8_t[]>(bytes.size());
    std::memcpy(buffer.get(), bytes.data(), bytes.size());
    return buffer;
}

std::unique_ptr<char[]> copy_string_to_buffer(std::string_view text) {
    if (text.empty())
        return {};
    auto buffer = std::make_unique<char[]>(text.size() + 1);
    std::memcpy(buffer.get(), text.data(), text.size());
    buffer[text.size()] = '\0';
    return buffer;
}

template <typename T>
std::unique_ptr<T[]> make_zeroed_array(size_t count) {
    if (count == 0)
        return {};
    return std::make_unique<T[]>(count);
}

}  // namespace

bool fill_result_from_execution(const ExecutionResult& in, FE_Result* out) {
    if (!out)
        return false;

    try {
        FE_Result tmp{};
        tmp.success = in.success ? 1 : 0;
        tmp.instructions_executed = in.instructions_executed;
        tmp.memory_accesses = in.memory_accesses;

        auto error_message = copy_string_to_buffer(in.error_message);
        auto program_stdout = copy_string_to_buffer(in.program_stdout);
        auto program_stderr = copy_string_to_buffer(in.program_stderr);

        tmp.error_message = error_message.get();
        tmp.program_stdout = program_stdout.get();
        tmp.program_stderr = program_stderr.get();

        const size_t fd_count = in.fd_outputs.size();
        auto fd_outputs = make_zeroed_array<FE_FdOutput>(fd_count);
        std::vector<std::unique_ptr<char[]>> fd_aliases(fd_count);
        std::vector<std::unique_ptr<uint8_t[]>> fd_data(fd_count);
        tmp.fd_outputs_count = fd_count;
        tmp.fd_outputs = fd_outputs.get();

        size_t fd_idx = 0;
        for (const auto& [fd, capture] : in.fd_outputs.entries()) {
            tmp.fd_outputs[fd_idx].fd = fd;
            tmp.fd_outputs[fd_idx].size = capture.data.size();

            fd_aliases[fd_idx] = copy_string_to_buffer(capture.alias);
            fd_data[fd_idx] = copy_raw_bytes_to_buffer(capture.data);

            tmp.fd_outputs[fd_idx].alias = fd_aliases[fd_idx].get();
            tmp.fd_outputs[fd_idx].data = fd_data[fd_idx].get();
            ++fd_idx;
        }

        const size_t changed_count = in.changed_regs.size();
        auto changed_registers = make_zeroed_array<FE_ChangedRegister>(changed_count);
        std::vector<std::unique_ptr<char[]>> changed_names(changed_count);
        tmp.changed_registers_count = changed_count;
        tmp.changed_registers = changed_registers.get();

        size_t changed_idx = 0;
        for (const auto& [name, values] : in.changed_regs) {
            changed_names[changed_idx] = copy_string_to_buffer(name);
            tmp.changed_registers[changed_idx].name = changed_names[changed_idx].get();
            tmp.changed_registers[changed_idx].before = values.first;
            tmp.changed_registers[changed_idx].after = values.second;
            ++changed_idx;
        }

        const size_t patch_count = in.memory_patches.size();
        auto memory_patches = make_zeroed_array<FE_MemoryPatchOut>(patch_count);
        std::vector<std::unique_ptr<uint8_t[]>> patch_before(patch_count);
        std::vector<std::unique_ptr<uint8_t[]>> patch_after(patch_count);
        tmp.memory_patches_count = patch_count;
        tmp.memory_patches = memory_patches.get();
        for (size_t index = 0; index < patch_count; ++index) {
            const auto& patch = in.memory_patches[index];
            tmp.memory_patches[index].address = patch.address;
            tmp.memory_patches[index].before_size = patch.before.size();
            tmp.memory_patches[index].after_size = patch.after.size();

            patch_before[index] = copy_bytes_to_buffer(patch.before);
            patch_after[index] = copy_bytes_to_buffer(patch.after);
            tmp.memory_patches[index].before = patch_before[index].get();
            tmp.memory_patches[index].after = patch_after[index].get();
        }

        *out = tmp;

        error_message.release();
        program_stdout.release();
        program_stderr.release();
        fd_outputs.release();
        changed_registers.release();
        memory_patches.release();
        for (auto& alias : fd_aliases)
            alias.release();
        for (auto& bytes : fd_data)
            bytes.release();
        for (auto& name : changed_names)
            name.release();
        for (auto& before : patch_before)
            before.release();
        for (auto& after : patch_after)
            after.release();
        return true;
    } catch (...) {
        return false;
    }
}

void free_result_buffers(FE_Result* out) {
    if (!out)
        return;

    for (size_t index = 0; index < out->fd_outputs_count; ++index) {
        std::unique_ptr<uint8_t[]> data(out->fd_outputs[index].data);
        std::unique_ptr<char[]> alias(out->fd_outputs[index].alias);
    }
    for (size_t index = 0; index < out->changed_registers_count; ++index) {
        std::unique_ptr<char[]> name_copy(const_cast<char*>(out->changed_registers[index].name));
    }
    for (size_t index = 0; index < out->memory_patches_count; ++index) {
        std::unique_ptr<uint8_t[]> before(out->memory_patches[index].before);
        std::unique_ptr<uint8_t[]> after(out->memory_patches[index].after);
    }

    std::unique_ptr<char[]> error_message(const_cast<char*>(out->error_message));
    std::unique_ptr<char[]> stdout_buffer(out->program_stdout);
    std::unique_ptr<char[]> stderr_buffer(out->program_stderr);
    std::unique_ptr<FE_FdOutput[]> fd_outputs(out->fd_outputs);
    std::unique_ptr<FE_ChangedRegister[]> changed_registers(out->changed_registers);
    std::unique_ptr<FE_MemoryPatchOut[]> memory_patches(out->memory_patches);

    std::memset(out, 0, sizeof(*out));
}

}  // namespace fragment::api
