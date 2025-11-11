#include "fragment/cli.hpp"

#include <algorithm>
#include <cctype>
#include <functional>
#include <iostream>
#include <sstream>
#include <string_view>
#include <unordered_map>

#include "fragment/logging.hpp"

namespace fragment {

static uint64_t parse_input_value(const std::string& token) {
    if (token.size() > 2 && (token.substr(0, 2) == "0x" || token.substr(0, 2) == "0X"))
        return std::stoull(token, nullptr, 16);
    return std::stoull(token);
}

static void add_input_argument(const std::string& arg, std::map<std::string, uint64_t>& inputs) {
    size_t eq_pos = arg.find('=');
    if (eq_pos == std::string::npos)
        throw std::runtime_error("Argument --input invalide: " + arg);
    std::string reg = arg.substr(0, eq_pos);
    std::string value_token = arg.substr(eq_pos + 1);
    inputs[reg] = parse_input_value(value_token);
}

static std::vector<std::reference_wrapper<const PartitionInfo>> order_plan(
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

void print_usage(std::string_view prog) {
    std::cout << "Usage: " << prog
              << " <asm_file> [<asm_file> ...] [--input reg=value ...] [--native] [--log fichier]\n"
              << "   ou : " << prog
              << " --summary partitions/summary.json [--input reg=value ...] [--native] [--log fichier]\n\n"
              << "Exemples:\n"
              << "  " << prog << " partition.asm\n"
              << "  " << prog << " func_0.asm func_1.asm --input rax=42 rbx=100\n"
              << "  " << prog << " --summary partitions/summary.json --input rdi=0x1000\n\n"
              << "Options:\n"
              << "  --summary fichier : Charger le graphe d'exécution généré par splitter\n"
              << "  --input reg=value : Définir une valeur d'entrée pour un registre\n"
              << "  --native          : Exécution native (DANGEREUX!)\n"
              << "  --log fichier     : Capture uniquement la sortie stdout des fragments dans un fichier\n";
}

CliOptions parse_arguments(const std::vector<std::string_view>& args) {
    CliOptions opts;

    for (size_t i = 1; i < args.size(); ++i) {
        std::string arg(args[i]);

        if (arg == "--native")
            opts.native_mode = true;
        else if (arg == "--summary") {
            if (i + 1 >= args.size())
                throw std::runtime_error("Option --summary requiert un fichier (summary.json)");
            opts.summary_file = std::string(args[++i]);
        } else if (arg == "--input") {
            if (i + 1 >= args.size())
                throw std::runtime_error("Option --input requiert un argument de la forme reg=val");
            add_input_argument(std::string(args[++i]), opts.inputs);
        } else if (arg == "--log") {
            if (i + 1 >= args.size())
                throw std::runtime_error("Option --log requiert un fichier (ex: --log exec.log)");
            opts.log_path = std::string(args[++i]);
        } else if (arg == "--help")
            throw std::runtime_error("Option --help demandée");
        else
            opts.asm_files.push_back(arg);
    }

    return opts;
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
    plan.reserve(asm_files.size());

    for (const auto& file : asm_files) {
        ExecutionEntry entry;
        entry.name = file;
        entry.asm_path = file;
        plan.push_back(entry);
    }

    return plan;
}

void print_plan_overview(const std::string& summary_file,
                         const std::vector<ExecutionEntry>& plan) {
    log::section("Graphe chargé");

    std::cout << "Partitions: " << plan.size() << "\n";
    std::cout << "Fichier: " << summary_file << "\n";

    if (plan.empty())
        return;

    std::cout << "Ordre d'exécution: ";

    for (size_t i = 0; i < plan.size(); ++i) {
        if (i)
            std::cout << " -> ";
        std::cout << plan[i].name;
    }
    std::cout << "\n";
}

void describe_entry(size_t idx, const ExecutionEntry& entry) {
    log::section("Fragment " + std::to_string(idx) + " : " + entry.name);

    if (!entry.meta.has_value())
        return;

    const PartitionInfo& meta = entry.meta->get();

    if (!meta.parents.empty()) {
        std::cout << "  Parents: ";
        for (size_t p = 0; p < meta.parents.size(); ++p) {
            if (p)
                std::cout << ", ";
            std::cout << meta.parents[p];
        }
        std::cout << "\n";
    }

    if (!meta.dependencies.empty()) {
        std::cout << "  Dépendances internes: ";
        for (size_t d = 0; d < meta.dependencies.size(); ++d) {
            if (d)
                std::cout << ", ";
            std::cout << meta.dependencies[d];
        }
        std::cout << "\n";
    }

    if (!meta.unresolved_calls.empty()) {
        std::cout << "  Appels externes: ";
        for (size_t d = 0; d < meta.unresolved_calls.size(); ++d) {
            if (d)
                std::cout << ", ";
            std::cout << meta.unresolved_calls[d];
        }
        std::cout << "\n";
    }
}

void prepare_external_inputs(const ExecutionEntry& entry,
                             FragmentExecutor& executor,
                             const std::map<std::string, uint64_t>& inputs,
                             std::set<std::string>& consumed_inputs) {
    if (!entry.meta.has_value())
        return;

    const PartitionInfo& meta = entry.meta->get();

    if (meta.external_inputs.empty())
        return;

    log::subsection("Préparation des entrées externes");

    for (const auto& reg : meta.external_inputs) {
        auto it = inputs.find(reg);
        if (it != inputs.end()) {
            executor.set_input(reg, it->second);
            consumed_inputs.insert(reg);
            std::cout << "    - " << reg << " = 0x" << std::hex << it->second
                      << std::dec << " (" << it->second << ") via --input\n";
        } else {
            uint64_t current_value = executor.get_register(reg);
            std::cout << "    - " << reg << " (valeur actuelle) = 0x" << std::hex
                      << current_value << std::dec << " (" << current_value << ")\n";
        }
    }
}

std::string derive_binary_path(const ExecutionEntry& entry) {
    if (entry.meta && !entry.meta->get().bin_path.empty())
        return entry.meta->get().bin_path;

    std::string path = entry.asm_path;
    size_t dot_pos = path.rfind('.');
    if (dot_pos != std::string::npos)
        path = path.substr(0, dot_pos);
    return path + ".bin";
}

bool execute_entry(const ExecutionEntry& entry,
                   bool native_mode,
                   FragmentExecutor& executor,
                   ExecutionResult& result) {
    if (!native_mode) {
        result = executor.execute_safe(entry.asm_path);
        return true;
    }

    const std::string bin_file = derive_binary_path(entry);
    std::ifstream file(bin_file, std::ios::binary);
    if (!file) {
        log::error("Impossible d'ouvrir " + bin_file);
        return false;
    }

    std::vector<uint8_t> binary_code((std::istreambuf_iterator<char>(file)),
                                     std::istreambuf_iterator<char>());
    result = executor.execute_native(binary_code);
    return true;
}

void log_program_output(std::ofstream& log_stream, const ExecutionResult& result) {
    if (!log_stream || result.program_stdout.empty())
        return;
    log_stream << result.program_stdout;
    log_stream.flush();
}

void warn_unused_inputs(const std::set<std::string>& expected,
                        const std::set<std::string>& consumed,
                        const std::map<std::string, uint64_t>& inputs) {
    std::vector<std::string> unused;

    for (const auto& [reg, value] : inputs) {
        (void)value;
        if (!expected.count(reg))
            continue;
        if (!consumed.count(reg))
            unused.push_back(reg);
    }

    if (unused.empty())
        return;

    log::warning("Valeurs --input non consommées (aucune partition ne les demande directement):");

    std::cout << "  ";

    for (size_t i = 0; i < unused.size(); ++i) {
        if (i)
            std::cout << ", ";
        std::cout << unused[i];
    }
    std::cout << "\n";
}

}  // namespace fragment
