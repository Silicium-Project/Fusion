#include "worker/io/Reporter.hpp"

#include <iomanip>
#include <iostream>
#include <sstream>

#include "worker/core/WorkerConfig.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker {

static std::string format_bytes(const std::vector<uint8_t>& bytes, size_t limit = 16) {
    std::ostringstream oss;
    for (size_t i = 0; i < bytes.size() && i < limit; ++i) {
        if (i)
            oss << ' ';
        oss << std::hex << std::setw(2) << std::setfill('0')
            << static_cast<int>(bytes[i]);
    }
    if (bytes.size() > limit)
        oss << " ...";
    return oss.str();
}

static std::string escape_json(std::string_view input) {
    std::string out;
    out.reserve(input.size() + 4);

    for (char c : input) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    std::ostringstream oss;
                    oss << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(static_cast<unsigned char>(c));
                    out += oss.str();
                } else {
                    out.push_back(c);
                }
        }
    }

    return out;
}

void dump_changed_registers_text(std::ostream& os,
                                 const std::map<std::string, std::pair<uint64_t, uint64_t>>& regs) {
    if (regs.empty()) {
        os << "  Registres modifiés: aucun\n";
        return;
    }

    os << "  Registres modifiés:\n";
    for (const auto& [name, values] : regs) {
        os << "    - " << name << ": 0x"
           << std::hex << values.first << " -> 0x" << values.second << std::dec << "\n";
    }
}

Reporter::Reporter(OutputFormat format, std::ostream& stream)
: format_(format)
, stream_(&stream) {}

void Reporter::emit(const WorkerReport& report) {
    if (!stream_)
        return;

    if (format_ == OutputFormat::Json)
        emit_json(report);
    else
        emit_text(report);
}

void Reporter::emit_text(const WorkerReport& report) {
    *stream_ << "Résumé: " << report.summary_path << "\n";
    auto mode_label = [](ExecutionMode mode) {
        switch (mode) {
            case ExecutionMode::Dynamo: return "dynamo";
            case ExecutionMode::Native: return "native";
            case ExecutionMode::Emulator: return "émulation";
            case ExecutionMode::Auto: default: return "auto";
        }
    };
    *stream_ << "Mode: " << mode_label(report.mode) << "\n";
    *stream_ << "Tâches: " << report.tasks.size() << "\n";

    for (const auto& task : report.tasks) {
        const auto& telemetry = task.telemetry;
        const std::string status = telemetry.status.empty()
            ? (task.result.success ? "success" : "failure")
            : telemetry.status;
        const std::string task_id = telemetry.task_id.empty()
            ? task.partition_id
            : telemetry.task_id;
        const std::string linux_policy = telemetry.linux_policy.empty()
            ? "unknown"
            : telemetry.linux_policy;
        const std::string windows_policy = telemetry.windows_policy.empty()
            ? "unknown"
            : telemetry.windows_policy;
        const std::string wsl_decision = telemetry.wsl_decision.empty()
            ? "unknown"
            : telemetry.wsl_decision;

        *stream_ << "\n==============================\n";
        *stream_ << "Task ID: " << task_id << "\n";
        *stream_ << "Type: " << task_type_to_string(telemetry.type) << "\n";
        *stream_ << "Status: " << status << "\n";
        *stream_ << "Durée: " << telemetry.duration_ms << " ms\n";
        *stream_ << "Policy: linux=" << linux_policy << " windows=" << windows_policy << "\n";
        *stream_ << "WSL: " << (telemetry.wsl_enabled ? "on" : "off")
                 << " (" << wsl_decision << ")\n";
        *stream_ << "Partition: " << task.partition_id << "\n";
        *stream_ << "Entrées:";
        if (task.inputs.empty())
            *stream_ << " aucune\n";
        else {
            *stream_ << "\n";
            for (const auto& [reg, val] : task.inputs) {
                *stream_ << "  - " << reg << " = 0x"
                         << std::hex << val << std::dec << " (" << val << ")\n";
            }
        }

        *stream_ << "Résultat: " << (task.result.success ? "OK" : "ÉCHEC") << "\n";
        if (!task.result.error_message.empty())
            *stream_ << "  => " << task.result.error_message << "\n";

        *stream_ << "  Instructions exécutées: " << task.result.instructions_executed << "\n";
        *stream_ << "  Accès mémoire: " << task.result.memory_accesses << "\n";

        dump_changed_registers_text(*stream_, task.result.changed_regs);

        if (!task.result.program_stdout.empty())
            *stream_ << "  Sortie fragment:\n" << task.result.program_stdout;
        if (!task.result.program_stderr.empty())
            *stream_ << "  Erreur fragment:\n" << task.result.program_stderr;
        if (!task.result.fd_outputs.empty()) {
            *stream_ << "  FDs capturés:\n";
            for (const auto& [fd, cap] : task.result.fd_outputs) {
                *stream_ << "    fd " << fd;
                if (!cap.alias.empty())
                    *stream_ << " (" << cap.alias << ")";
                *stream_ << " (" << cap.data.size() << " octets)\n";
            }
        }

        if (!task.result.memory_patches.empty()) {
            *stream_ << "  Écritures mémoire:\n";
            for (const auto& patch : task.result.memory_patches) {
                *stream_ << "    @0x" << std::hex << patch.address << std::dec
                         << " (" << patch.after.size() << " octets)\n";
                *stream_ << "      avant : " << format_bytes(patch.before) << "\n";
                *stream_ << "      après : " << format_bytes(patch.after) << "\n";
            }
        }
    }

    *stream_ << "\n";
}

void Reporter::emit_json(const WorkerReport& report) {
    std::ostringstream oss;
    oss << "{";
    oss << "\"summary\":\"" << escape_json(report.summary_path) << "\",";
    auto mode_label = [](ExecutionMode mode) {
        switch (mode) {
            case ExecutionMode::Dynamo: return "dynamo";
            case ExecutionMode::Native: return "native";
            case ExecutionMode::Emulator: return "emu";
            case ExecutionMode::Auto: default: return "auto";
        }
    };
    oss << "\"mode\":\"" << mode_label(report.mode) << "\",";
    oss << "\"tasks\":[";

    for (size_t i = 0; i < report.tasks.size(); ++i) {
        const auto& task = report.tasks[i];
        if (i)
            oss << ",";
        const auto& telemetry = task.telemetry;
        const std::string status = telemetry.status.empty()
            ? (task.result.success ? "success" : "failure")
            : telemetry.status;
        const std::string task_id = telemetry.task_id.empty()
            ? task.partition_id
            : telemetry.task_id;
        const std::string linux_policy = telemetry.linux_policy.empty()
            ? "unknown"
            : telemetry.linux_policy;
        const std::string windows_policy = telemetry.windows_policy.empty()
            ? "unknown"
            : telemetry.windows_policy;
        const std::string wsl_decision = telemetry.wsl_decision.empty()
            ? "unknown"
            : telemetry.wsl_decision;
        oss << "{";
        oss << "\"task_id\":\"" << escape_json(task_id) << "\",";
        oss << "\"type\":\"" << escape_json(task_type_to_string(telemetry.type)) << "\",";
        oss << "\"status\":\"" << escape_json(status) << "\",";
        oss << "\"started_at_ms\":" << telemetry.started_at_ms << ",";
        oss << "\"finished_at_ms\":" << telemetry.finished_at_ms << ",";
        oss << "\"duration_ms\":" << telemetry.duration_ms << ",";
        oss << "\"linux_policy\":\"" << escape_json(linux_policy) << "\",";
        oss << "\"windows_policy\":\"" << escape_json(windows_policy) << "\",";
        oss << "\"wsl_enabled\":" << (telemetry.wsl_enabled ? "true" : "false") << ",";
        oss << "\"wsl_decision\":\"" << escape_json(wsl_decision) << "\",";
        oss << "\"warnings\":[";
        for (size_t w = 0; w < telemetry.warnings.size(); ++w) {
            if (w)
                oss << ",";
            oss << "\"" << escape_json(telemetry.warnings[w]) << "\"";
        }
        oss << "],";
        oss << "\"partition\":\"" << escape_json(task.partition_id) << "\",";
        oss << "\"success\":" << (task.result.success ? "true" : "false") << ",";
        oss << "\"error\":\"" << escape_json(task.result.error_message) << "\",";
        oss << "\"instructions\":" << task.result.instructions_executed << ",";
        oss << "\"memory_accesses\":" << task.result.memory_accesses << ",";
        oss << "\"stdout\":\"" << escape_json(task.result.program_stdout) << "\",";
        oss << "\"stderr\":\"" << escape_json(task.result.program_stderr) << "\",";
        oss << "\"fd_outputs\":{";
        size_t fd_idx = 0;
        for (const auto& [fd, cap] : task.result.fd_outputs) {
            if (fd_idx++)
                oss << ",";
            oss << "\"" << fd << "\":{"
                << "\"data\":\"" << escape_json(cap.data) << "\"";
            if (!cap.alias.empty())
                oss << ",\"alias\":\"" << escape_json(cap.alias) << "\"";
            oss << "}";
        }
        oss << "},";
        oss << "\"inputs\":{";
        size_t input_idx = 0;
        for (const auto& [reg, val] : task.inputs) {
            if (input_idx++)
                oss << ",";
            oss << "\"" << escape_json(reg) << "\":" << val;
        }
        oss << "},";
        oss << "\"changed_registers\":[";
        size_t reg_idx = 0;
        for (const auto& [name, values] : task.result.changed_regs) {
            if (reg_idx++)
                oss << ",";
            oss << "{"
                << "\"name\":\"" << escape_json(name) << "\","
                << "\"before\":" << values.first << ","
                << "\"after\":" << values.second
                << "}";
        }
        oss << "]";
        oss << ",\"memory_patches\":[";
        size_t patch_idx = 0;
        for (const auto& patch : task.result.memory_patches) {
            if (patch_idx++)
                oss << ",";
            oss << "{"
                << "\"address\":" << patch.address << ","
                << "\"size\":" << patch.after.size() << ","
                << "\"before\":\"" << escape_json(format_bytes(patch.before, patch.before.size())) << "\","
                << "\"after\":\"" << escape_json(format_bytes(patch.after, patch.after.size())) << "\""
                << "}";
        }
        oss << "]";
        oss << "}";
    }

    oss << "]}";
    *stream_ << oss.str() << "\n";
}

}  // namespace worker
