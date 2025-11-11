#include <fstream>
#include <iostream>
#include <set>
#include <vector>

#include "fragment/cli.hpp"
#include "fragment/logging.hpp"
#include "fragment/runner.hpp"

namespace fragment {

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

    FragmentExecutor executor(opts.native_mode);
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
        try {
            execution_plan = plan_from_summary(partition_infos, expected_external_inputs);
        } catch (const std::exception& e) {
            log::error(std::string("Cycle détecté dans le graphe: ") + e.what());
            return 1;
        }
        if (!summary.binary_path.empty())
            executor.set_binary_path(summary.binary_path);
        print_plan_overview(opts.summary_file, execution_plan);
    } else {
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
        prepare_external_inputs(entry, executor, opts.inputs, consumed_external_inputs);

        if (!execute_entry(entry, opts.native_mode, executor, last_result)) {
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

    return all_success ? 0 : 1;
}

}  // namespace fragment
