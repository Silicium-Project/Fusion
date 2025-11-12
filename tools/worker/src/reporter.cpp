#include "worker/reporter.hpp"

#include <iomanip>
#include <iostream>
#include <sstream>

namespace worker {

namespace {

std::string format_bytes(const std::vector<uint8_t>& bytes, size_t limit = 16) {
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

std::string escape_json(std::string_view input) {
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

}  // namespace

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
    *stream_ << "Mode: " << (report.native_mode ? "native" : "émulation") << "\n";
    *stream_ << "Tâches: " << report.tasks.size() << "\n";

    for (const auto& task : report.tasks) {
        *stream_ << "\n==============================\n";
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
    oss << "\"mode\":\"" << (report.native_mode ? "native" : "safe") << "\",";
    oss << "\"tasks\":[";

    for (size_t i = 0; i < report.tasks.size(); ++i) {
        const auto& task = report.tasks[i];
        if (i)
            oss << ",";
        oss << "{";
        oss << "\"partition\":\"" << escape_json(task.partition_id) << "\",";
        oss << "\"success\":" << (task.result.success ? "true" : "false") << ",";
        oss << "\"error\":\"" << escape_json(task.result.error_message) << "\",";
        oss << "\"instructions\":" << task.result.instructions_executed << ",";
        oss << "\"memory_accesses\":" << task.result.memory_accesses << ",";
        oss << "\"stdout\":\"" << escape_json(task.result.program_stdout) << "\",";
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
