#include "fragment/cli.hpp"
#include "fragment/logging.hpp"
#include "fragment/runner.hpp"

#include <set>

#ifdef __linux__
#include <dlfcn.h>
#endif

namespace fragment {

namespace {

void preload_initial_memory(const PartitionSummary& summary, FragmentExecutor& executor) {
    for (const auto& region : summary.initial_memory) {
        executor.apply_memory_bytes(region.address, region.bytes);
        executor.preload_native_chunk(region.address, region.bytes);
    }
}

#ifdef __linux__
void ensure_required_libraries(const PartitionSummary& summary) {
    std::set<std::string> libraries(summary.required_libraries.begin(),
                                    summary.required_libraries.end());
    for (const auto& partition : summary.partitions)
        libraries.insert(partition.required_libraries.begin(),
                         partition.required_libraries.end());

    for (const auto& lib : libraries) {
        if (lib.empty())
            continue;
        void* handle = dlopen(lib.c_str(), RTLD_LAZY | RTLD_GLOBAL);
        if (!handle) {
            const char* err = dlerror();
            log::warning("Impossible de charger la bibliothèque " + lib + ": "
                         + (err ? err : "motif inconnu"));
        }
    }
}
#else
void ensure_required_libraries(const PartitionSummary&) {}
#endif

}  // namespace

int run_cli(const std::vector<std::string_view>& args) {
    if (args.size() < 2) {
        std::string_view prog = args.empty() ? "fragment_executor" : args.front();
        print_usage(prog);
        return 1;
    }

    CliOptions opts;
    try {
        opts = parse_arguments(args);
    } catch (const std::exception& e) {
        log::error(std::string("Analyse des arguments: ") + e.what());
        print_usage(args.front());
        return 1;
    }

    if (!opts.summary_file.empty() && !opts.asm_files.empty()) {
        log::error("Choisir soit des fichiers ASM, soit un fichier --summary, mais pas les deux.");
        return 1;
    }
    if (opts.summary_file.empty() && opts.asm_files.empty()) {
        log::error("Aucun fichier ASM ni fichier résumé fourni.");
        print_usage(args.front());
        return 1;
    }

    std::ofstream program_log;
    if (!opts.log_path.empty() && !open_log_file(opts.log_path, program_log))
        log::warning("Impossible d'ouvrir le fichier de log: " + opts.log_path);

    ExecutorConfig exec_cfg;
    exec_cfg.use_native_execution = opts.native_mode;
    FragmentExecutor executor(exec_cfg);
    std::vector<ExecutionEntry> execution_plan;
    std::set<std::string> expected_external_inputs;
    std::vector<PartitionInfo> partition_infos;

    if (!opts.summary_file.empty()) {
        PartitionSummary summary;
        try {
            summary = load_partition_summary(opts.summary_file);
        } catch (const std::exception& e) {
            log::error(std::string("Erreur lors du chargement du graphe: ") + e.what());
            return 1;
        }
        partition_infos = summary.partitions;
        set_partition_registry(&partition_infos);
        try {
            execution_plan = plan_from_summary(partition_infos, expected_external_inputs);
        } catch (const std::exception& e) {
            log::error(std::string("Cycle détecté dans le graphe: ") + e.what());
            return 1;
        }
        if (!summary.binary_path.empty())
            executor.set_binary_path(summary.binary_path);
        preload_initial_memory(summary, executor);
        if (opts.native_mode)
            ensure_required_libraries(summary);
        print_plan_overview(opts.summary_file, execution_plan);
    } else {
        set_partition_registry(nullptr);
        execution_plan = plan_from_files(opts.asm_files);
    }

    log::banner();
    apply_inputs(executor, opts.inputs);

    log::section("État initial des registres");
    executor.print_register_state();

    std::set<std::string> consumed_external_inputs;
    ExecutionResult last_result;
    bool all_success = true;

    for (size_t idx = 0; idx < execution_plan.size(); ++idx) {
        const auto& entry = execution_plan[idx];

        describe_entry(idx, entry);
        bool missing_inputs = prepare_external_inputs(entry, executor, opts.inputs, consumed_external_inputs);

        bool entry_native_mode = opts.native_mode && (!missing_inputs || opts.force_native);
        if (opts.native_mode && missing_inputs && !opts.force_native)
            log::warning("Entrées externes manquantes pour " + entry.name
                         + " - repli sur l'émulation sécurisée.");
        else if (opts.native_mode && missing_inputs && opts.force_native)
            log::warning("Entrées externes manquantes pour " + entry.name
                         + ", exécution native forcée.");

        if (!execute_entry(entry, entry_native_mode, opts.force_native, executor, last_result)) {
            all_success = false;
            break;
        }

        log::section("Résultats");
        last_result.print();
        log_program_output(program_log, last_result);

        if (!last_result.success) {
            all_success = false;
            log::error("Arrêt: échec de l'exécution pour " + entry.asm_path);
            break;
        }
    }

    if (all_success) {
        log::section("État final des registres");
        executor.print_register_state();
    }

    if (!opts.summary_file.empty() && !opts.inputs.empty())
        warn_unused_inputs(expected_external_inputs, consumed_external_inputs, opts.inputs);

    set_partition_registry(nullptr);
    return all_success ? 0 : 1;
}

}  // namespace fragment
