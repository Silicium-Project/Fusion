#include "cli/Cli.hpp"

#include "support/Logging.hpp"
#include "partition/PartitionRegistry.hpp"
#include "partition/PartitionSummary.hpp"
#include "support/Utils.hpp"
#include "backend/ExecutionBackend.hpp"

#include <fstream>
#include <functional>
#include <iterator>
#include <set>
#include <unordered_map>
#include <unordered_set>

namespace fragment {

namespace {

PartitionRegistry& registry() {
    return global_partition_registry();
}

std::string derive_binary_path(const PartitionInfo& info) {
    if (!info.bin_path.empty())
        return info.bin_path;
    std::string path = info.asm_path;
    size_t dot_pos = path.rfind('.');
    if (dot_pos != std::string::npos)
        path = path.substr(0, dot_pos);
    return path + ".bin";
}

std::vector<std::reference_wrapper<const PartitionInfo>> order_plan(
        const std::vector<PartitionInfo>& partitions) {
    std::vector<std::reference_wrapper<const PartitionInfo>> ordered;
    auto ids = order_partitions(partitions);
    std::unordered_map<std::string, std::reference_wrapper<const PartitionInfo>> lookup;
    for (const auto& partition : partitions)
        lookup.emplace(partition.id, std::cref(partition));

    ordered.reserve(ids.size());
    for (const auto& id : ids) {
        auto it = lookup.find(id);
        if (it != lookup.end())
            ordered.push_back(it->second);
    }
    return ordered;
}

}  // namespace

void set_partition_registry(const std::vector<PartitionInfo>* partitions) {
    registry().set(partitions);
}

void print_usage(std::string_view prog) {
    std::cout << "Usage: " << prog
              << " <asm_file> [<asm_file> ...] [--input reg=value ...] [--native] [--log fichier]\n"
              << "   ou : " << prog
              << " --summary partitions/summary.json [--input reg=value ...] [--native] [--native-force] [--skip-memory-check] [--log fichier]\n\n"
              << "Exemples:\n"
              << "  " << prog << " partition.asm\n"
              << "  " << prog << " func_0.asm func_1.asm --input rax=42 rbx=100\n"
              << "  " << prog << " --summary partitions/summary.json --input rdi=0x1000\n\n"
              << "Options:\n"
              << "  --native          : Active l'exécution native (pas de repli automatique)\n"
              << "  --native-force   : Force le natif même si entrées manquantes/appels externes\n"
              << "  --skip-memory-check : Ignore les vérifications d'empreinte mémoire du summary\n"
              << "  --log fichier     : Capture uniquement la sortie stdout des fragments dans un fichier\n";
}

bool open_log_file(const std::string& path, std::ofstream& stream) {
    stream.open(path, std::ios::out | std::ios::trunc);
    return static_cast<bool>(stream);
}

void apply_inputs(FragmentExecutor& executor, const std::map<std::string, uint64_t>& inputs) {
    if (inputs.empty())
        return;

    log::section("Valeurs d'entrée");

    for (const auto& [reg, val] : inputs) {
        std::cout << "  " << reg << " = 0x" << std::hex << val << std::dec << " (" << val << ")\n";
        executor.set_input(reg, val);
    }
}

std::vector<ExecutionEntry> plan_from_summary(const std::vector<PartitionInfo>& partitions,
                                              std::set<std::string>& expected_inputs) {
    std::vector<ExecutionEntry> plan;
    auto ordered = order_plan(partitions);

    plan.reserve(ordered.size());
    for (const auto& info_ref : ordered) {
        const auto& info = info_ref.get();
        ExecutionEntry entry;
        entry.name = info.id;
        entry.asm_path = info.asm_path;
        entry.meta = std::cref(info);

        plan.push_back(entry);
        expected_inputs.insert(info.external_inputs.begin(), info.external_inputs.end());
    }

    return plan;
}

std::vector<ExecutionEntry> plan_from_files(const std::vector<std::string>& asm_files) {
    std::vector<ExecutionEntry> plan;

    for (const auto& file : asm_files) {
        ExecutionEntry entry;
        entry.name = file;
        entry.asm_path = file;
        plan.push_back(std::move(entry));
    }
    return plan;
}

void print_plan_overview(const std::string& summary_file, const std::vector<ExecutionEntry>& plan) {
    std::cout << "============================================================\n"
              << " Graphe chargé\n"
              << "============================================================\n"
              << "Partitions: " << plan.size() << "\n"
              << "Fichier: " << summary_file << "\n"
              << "Ordre d'exécution: ";
    for (size_t i = 0; i < plan.size(); ++i) {
        if (i)
            std::cout << " -> ";
        std::cout << plan[i].name;
    }
    std::cout << "\n\n";
}

void describe_entry(size_t idx, const ExecutionEntry& entry) {
    log::section("Fragment " + std::to_string(idx) + " : " + entry.name);
    if (entry.meta.has_value()) {
        const auto& meta = entry.meta->get();
        if (!meta.dependencies.empty()) {
            std::cout << "  Dépendances internes:";
            for (const auto& dep : meta.dependencies)
                std::cout << " " << dep;
            std::cout << "\n";
        }
        if (!meta.unresolved_calls.empty()) {
            std::cout << "  Appels externes:";
            for (const auto& call : meta.unresolved_calls)
                std::cout << " " << call;
            std::cout << "\n";
        }
    }
}

bool prepare_external_inputs(const ExecutionEntry& entry,
                             FragmentExecutor& executor,
                             const std::map<std::string, uint64_t>& inputs,
                             std::set<std::string>& consumed_inputs) {

    if (!entry.meta.has_value())
        return false;

    const auto& meta = entry.meta->get();
    bool missing = false;

    for (const auto& reg : meta.external_inputs) {
        auto it = inputs.find(reg);
        if (it == inputs.end()) {
            missing = true;
            continue;
        }
        executor.set_input(reg, it->second);
        consumed_inputs.insert(reg);
    }
    return missing;
}

std::string derive_binary_path(const ExecutionEntry& entry) {
    if (entry.meta)
        return derive_binary_path(entry.meta->get());

    std::string path = entry.asm_path;
    size_t dot_pos = path.rfind('.');
    if (dot_pos != std::string::npos)
        path = path.substr(0, dot_pos);
    return path + ".bin";
}

bool execute_entry(const ExecutionEntry& entry,
                   bool native_mode,
                   bool force_native,
                   FragmentExecutor& executor,
                   ExecutionResult& result) {
    static std::unique_ptr<ExecutionBackendFactory> factory = make_backend_factory();
    auto backend = factory->create(native_mode, force_native);
    return backend->run(entry, executor, result);
}

void log_program_output(std::ofstream& log_stream, const ExecutionResult& result) {
    if (!log_stream)
        return;
    if (!result.program_stdout.empty())
        log_stream << result.program_stdout;
    if (!result.program_stderr.empty())
        log_stream << result.program_stderr;
    log_stream.flush();
}

void warn_unused_inputs(const std::set<std::string>& expected,
                        const std::set<std::string>& consumed,
                        const std::map<std::string, uint64_t>& inputs) {
    if (inputs.empty())
        return;
    for (const auto& [reg, val] : inputs)
        if (expected.count(reg) && !consumed.count(reg))
            log::warning("Entrée " + reg + " fournie mais non utilisée (valeur " + std::to_string(val) + ")");
}

}  // namespace fragment
