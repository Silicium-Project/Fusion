#include "backend/NativeExecutionBackend.hpp"

#include <unistd.h>

namespace fragment {

NativeExecutionBackend::NativeExecutionBackend(bool force_native)
: runner_(force_native) {}

bool NativeExecutionBackend::run(const ExecutionEntry& entry,
                                 FragmentExecutor& executor,
                                 ExecutionResult& result) const {
    bool ok = runner_.run(entry, executor, result);
    if (ok && result.program_stdout.empty() && result.program_stderr.empty() && result.fd_outputs.empty()) {
        // Best-effort capture stdout/stderr/FDs même pour le natif.
        auto pipes = executor.capture_program_pipes([&]() {
            ExecutionResult tmp;
            runner_.run(entry, executor, tmp);
        });
        if (pipes.fds.contains(STDOUT_FILENO))
            result.program_stdout = pipes.fds.at(STDOUT_FILENO).data;
        if (pipes.fds.contains(STDERR_FILENO))
            result.program_stderr = pipes.fds.at(STDERR_FILENO).data;
        result.fd_outputs = std::move(pipes.fds);
    }
    return ok;
}

}  // namespace fragment
