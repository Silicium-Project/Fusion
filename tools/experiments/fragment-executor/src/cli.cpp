#include "fragment/cli.hpp"

#include "fragment/logging.hpp"
#include "fragment/utils.hpp"

#include <fstream>
#include <functional>
#include <iterator>
#include <unordered_map>
#include <unordered_set>
#ifdef __linux__
#include <dlfcn.h>
#endif

namespace fragment {

namespace {

const std::vector<PartitionInfo>* g_partition_registry = nullptr;
std::unordered_map<std::string, const PartitionInfo*> g_partition_lookup;
std::unordered_set<std::string> g_preloaded_dependencies;

const PartitionInfo* lookup_partition(const std::string& id) {
    auto it = g_partition_lookup.find(id);
    if (it == g_partition_lookup.end())
        return nullptr;
    return it->second;
}

std::vector<uint8_t> read_binary_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        log::warning("Impossible d'ouvrir " + path
                     + " pour initialiser les dépendances natives.");
        return {};
    }
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(file), {});
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

struct UnresolvedHook {
    uint64_t address = 0;
    std::string symbol;
};

std::optional<UnresolvedHook> parse_unresolved_descriptor(const std::string& desc) {
    size_t lt = desc.find('<');
    size_t gt = desc.find('>', lt == std::string::npos ? 0 : lt + 1);
    if (lt == std::string::npos || gt == std::string::npos)
        return std::nullopt;
    std::string addr_text = fragment::trim(desc.substr(0, lt));
    if (addr_text.empty())
        return std::nullopt;
    uint64_t addr = 0;
    try {
        addr = std::stoull(addr_text, nullptr, 16);
    } catch (...) {
        return std::nullopt;
    }
    std::string symbol = desc.substr(lt + 1, gt - lt - 1);
    auto at_pos = symbol.find('@');
    if (at_pos != std::string::npos)
        symbol = symbol.substr(0, at_pos);
    return UnresolvedHook{addr, symbol};
}

void preload_dependency_code(const PartitionInfo& meta, FragmentExecutor& executor) {
    if (!g_partition_registry)
        return;

    std::function<void(const PartitionInfo&)> loader = [&](const PartitionInfo& part) {
        for (const auto& dep_id : part.dependencies) {
            if (!g_preloaded_dependencies.insert(dep_id).second)
                continue;
            const PartitionInfo* dep = lookup_partition(dep_id);
            if (!dep) {
                log::warning("Partition dépendante inconnue: " + dep_id);
                continue;
            }
            if (!dep->start_address.has_value()) {
                log::warning("Adresse de départ manquante pour la partition dépendante: " + dep_id);
                continue;
            }
            const std::string bin_path = derive_binary_path(*dep);
            auto bytes = read_binary_file(bin_path);
            if (bytes.empty())
                continue;
            executor.preload_native_chunk(*dep->start_address, bytes);
            loader(*dep);
        }
    };

    loader(meta);
}

void install_unresolved_hooks(const PartitionInfo& meta, FragmentExecutor& executor) {
#ifdef __linux__
    for (const auto& call : meta.unresolved_calls) {
        auto info = parse_unresolved_descriptor(call);
        if (!info)
            continue;
        void* target = dlsym(RTLD_DEFAULT, info->symbol.c_str());
        if (!target)
            continue;
        uint64_t fn_addr = reinterpret_cast<uint64_t>(target);
        std::vector<uint8_t> stub;
        stub.reserve(12);
        stub.push_back(0x48);
        stub.push_back(0xB8);
        for (size_t idx = 0; idx < 8; ++idx)
            stub.push_back(static_cast<uint8_t>((fn_addr >> (idx * 8)) & 0xFF));
        stub.push_back(0xFF);
        stub.push_back(0xE0);
        executor.preload_native_chunk(info->address, stub);
    }
#else
    (void)meta;
    (void)executor;
#endif
}

}  // namespace

void set_partition_registry(const std::vector<PartitionInfo>* partitions) {
    g_partition_registry = partitions;
    g_partition_lookup.clear();
    g_preloaded_dependencies.clear();
    if (!g_partition_registry)
        return;
    for (const auto& partition : *g_partition_registry)
        g_partition_lookup.emplace(partition.id, &partition);
}

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
              << " --summary partitions/summary.json [--input reg=value ...] [--native] [--native-force] [--log fichier]\n\n"
              << "Exemples:\n"
              << "  " << prog << " partition.asm\n"
              << "  " << prog << " func_0.asm func_1.asm --input rax=42 rbx=100\n"
              << "  " << prog << " --summary partitions/summary.json --input rdi=0x1000\n\n"
              << "Options:\n"
              << "  --summary fichier : Charger le graphe d'exécution généré par splitter\n"
              << "  --input reg=value : Définir une valeur d'entrée pour un registre\n"
              << "  --native          : Exécution native (DANGEREUX!)\n"
              << "  --native-force   : Ignore les garde-fous natifs (extrêmement risqué)\n"
              << "  --log fichier     : Capture uniquement la sortie stdout des fragments dans un fichier\n";
}

CliOptions parse_arguments(const std::vector<std::string_view>& args) {
    CliOptions opts;

    for (size_t i = 1; i < args.size(); ++i) {
        std::string arg(args[i]);

        if (arg == "--native")
            opts.native_mode = true;
        else if (arg == "--native-force") {
            opts.native_mode = true;
            opts.force_native = true;
        }
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

bool prepare_external_inputs(const ExecutionEntry& entry,
                             FragmentExecutor& executor,
                             const std::map<std::string, uint64_t>& inputs,
                             std::set<std::string>& consumed_inputs) {
    if (!entry.meta.has_value())
        return false;

    const PartitionInfo& meta = entry.meta->get();

    if (meta.external_inputs.empty())
        return false;

    bool missing = false;

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
            missing = true;
        }
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
    if (native_mode && entry.meta.has_value()) {
        const auto& meta = entry.meta->get();
        const bool has_calls = !meta.unresolved_calls.empty();
        const bool has_deps = !meta.dependencies.empty();

        if ((has_calls || has_deps) && force_native) {
            log::warning("Fragment " + entry.name
                         + " contient des appels externes ou dépendances, exécution native forcée.");
        } else if (has_calls) {
            log::warning("Fragment " + entry.name
                         + " contient des appels externes ("
                         + std::to_string(meta.unresolved_calls.size())
                         + "), repli sur l'émulation sécurisée.");
            native_mode = false;
        } else if (has_deps) {
            log::warning("Fragment " + entry.name
                         + " dépend d'autres partitions ("
                         + std::to_string(meta.dependencies.size())
                         + "), repli sur l'émulation sécurisée.");
            native_mode = false;
        }
    }

    if (native_mode && entry.meta.has_value()) {
        preload_dependency_code(entry.meta->get(), executor);
        install_unresolved_hooks(entry.meta->get(), executor);
    }

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
    std::optional<uint64_t> original_address;
    if (entry.meta.has_value())
        original_address = entry.meta->get().start_address;
    result = executor.execute_native(binary_code, original_address);
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
