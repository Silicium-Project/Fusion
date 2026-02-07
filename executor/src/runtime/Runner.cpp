#include "cli/Cli.hpp"

#include "support/Logging.hpp"

#include "runtime/Runner.hpp"



#include <algorithm>

#include <optional>

#include <set>

#include <unistd.h>

#include <filesystem>

#include <unordered_map>



#ifdef __linux__

#include <dlfcn.h>

#endif



namespace fragment {



std::optional<std::string> default_gui_wrapper(const std::vector<std::string_view>& args);
bool partitions_require_gui(const std::vector<PartitionInfo>& partitions);
bool running_in_gui_wrapper();
bool reexec_in_gui_wrapper(const std::vector<std::string>& raw_args, const std::string& wrapper);

namespace {



void preload_initial_memory(const PartitionSummary& summary, FragmentExecutor& executor) {

    for (const auto& region : summary.initial_memory) {

        executor.apply_memory_bytes(region.address, region.bytes);

        executor.preload_native_chunk(region.address, region.bytes);

    }

}



#ifdef __linux__

void ensure_required_libraries(const PartitionSummary& summary) {

    std::unordered_map<std::string, std::string> path_by_name;

    for (const auto& lib : summary.libraries) {

        if (!lib.name.empty() && !lib.path.empty())

            path_by_name.emplace(lib.name, lib.path);

        if (!lib.soname.empty() && !lib.path.empty())

            path_by_name.emplace(lib.soname, lib.path);

    }



    std::set<std::string> libraries(summary.required_libraries.begin(),

                                    summary.required_libraries.end());

    for (const auto& partition : summary.partitions)

        libraries.insert(partition.required_libraries.begin(),

                         partition.required_libraries.end());



    for (const auto& lib : libraries) {

        if (lib.empty())

            continue;

        const auto it = path_by_name.find(lib);

        const std::string& candidate = (it != path_by_name.end()) ? it->second : lib;

        void* handle = dlopen(candidate.c_str(), RTLD_LAZY | RTLD_GLOBAL);

        if (!handle) {

            const char* err = dlerror();

            log::warning("Impossible de charger la bibliothÃ¨que " + candidate + ": "

                         + (err ? err : "motif inconnu"));

        }

    }

}

#else

void ensure_required_libraries(const PartitionSummary&) {}

#endif



struct Diagnostics {
    void error(const std::string& message) {
        log::error(message);
        last_error = message;
    }

    void warning(const std::string& message) {
        log::warning(message);
    }

    std::string last_error;
};

struct ExecutionPlanData {
    std::vector<ExecutionEntry> entries;
    std::set<std::string> expected_inputs;
    std::vector<PartitionInfo> partitions;
    bool from_summary = false;
};

static bool build_execution_plan(const CliOptions& opts,
                                const std::vector<std::string_view>& args,
                                const std::vector<std::string>& raw_args,
                                FragmentExecutor& executor,
                                ExecutionPlanData& plan,
                                Diagnostics& diag) {
    if (!opts.summary_file.empty()) {
        PartitionSummary summary;
        try {
            summary = load_partition_summary(opts.summary_file, opts.skip_memory_check);
        } catch (const std::exception& e) {
            diag.error(std::string("Erreur lors du chargement du graphe: ") + e.what());
            return false;
        }

        plan.partitions = summary.partitions;
        plan.from_summary = true;

        if (opts.native_mode && partitions_require_gui(plan.partitions) && !running_in_gui_wrapper()) {
            std::string wrapper_path;
            if (const char* wrapper_env = std::getenv("FRAGMENT_GUI_WRAPPER");
                wrapper_env && *wrapper_env) {
                wrapper_path = wrapper_env;
            } else if (auto fallback = default_gui_wrapper(args); fallback.has_value()) {
                wrapper_path = *fallback;
            }

            if (!wrapper_path.empty()) {
                if (reexec_in_gui_wrapper(raw_args, wrapper_path))
                    return false;
            } else {
                diag.warning("Fragments GUI d?tect?s mais aucun wrapper GUI n'est disponible.");
            }
        }

        set_partition_registry(&plan.partitions);
        try {
            plan.entries = plan_from_summary(plan.partitions, plan.expected_inputs);
        } catch (const std::exception& e) {
            diag.error(std::string("Cycle d?tect? dans le graphe: ") + e.what());
            return false;
        }

        if (!summary.binary_path.empty())
            executor.set_binary_path(summary.binary_path);
        preload_initial_memory(summary, executor);
        if (opts.native_mode)
            ensure_required_libraries(summary);
        print_plan_overview(opts.summary_file, plan.entries);
        return true;
    }

    set_partition_registry(nullptr);
    plan.entries = plan_from_files(opts.asm_files);
    plan.from_summary = false;
    return true;
}

static bool execute_plan(const CliOptions& opts,
                         FragmentExecutor& executor,
                         const ExecutionPlanData& plan,
                         std::ofstream& program_log,
                         ExecutionResult& last_result) {
    log::banner();
    apply_inputs(executor, opts.inputs);

    log::section("?tat initial des registres");
    executor.print_register_state();

    std::set<std::string> consumed_external_inputs;
    bool all_success = true;

    for (size_t idx = 0; idx < plan.entries.size(); ++idx) {
        const auto& entry = plan.entries[idx];

        describe_entry(idx, entry);
        bool missing_inputs = prepare_external_inputs(entry, executor, opts.inputs, consumed_external_inputs);

        bool has_external_calls = entry.meta && (!entry.meta->get().external_calls.empty() ||
                                                 !entry.meta->get().unresolved_calls.empty());
        if (opts.native_mode && missing_inputs && !opts.force_native) {
            last_result.success = false;
            last_result.error_message = "Ex?cution native bloqu?e: entr?es externes manquantes pour " + entry.name;
            log::error(last_result.error_message);
            all_success = false;
            break;
        }

        if (opts.native_mode && has_external_calls) {
            const std::string risk = missing_inputs
                ? "entr?es externes manquantes et appels externes/non r?solus"
                : "appels externes/non r?solus";
            log::warning("Ex?cution native malgr? " + risk + " sur " + entry.name
                         + " (pas de repli, risque de crash)." );
        }

        if (!execute_entry(entry, opts.native_mode, opts.force_native, executor, last_result)) {
            all_success = false;
            break;
        }

        log::section("R?sultats");
        last_result.print();
        log_program_output(program_log, last_result);

        if (!last_result.success) {
            all_success = false;
            log::error("Arr?t: ?chec de l'ex?cution pour " + entry.asm_path);
            break;
        }
    }

    if (all_success) {
        log::section("?tat final des registres");
        executor.print_register_state();
    }

    if (plan.from_summary && !opts.inputs.empty())
        warn_unused_inputs(plan.expected_inputs, consumed_external_inputs, opts.inputs);

    return all_success;
}

}  // namespace



std::optional<std::string> default_gui_wrapper(const std::vector<std::string_view>& args) {

    namespace fs = std::filesystem;

    if (args.empty())

        return std::nullopt;

    try {

        fs::path probe = fs::canonical(std::string(args.front())).parent_path();

        for (int i = 0; i < 5 && probe.has_parent_path(); ++i) {

            fs::path candidate = probe / "worker/scripts/gui_wrapper.sh";

            if (fs::exists(candidate))

                return candidate.string();

            probe = probe.parent_path();

        }

    } catch (...) {

    }

    return std::nullopt;

}



bool partitions_require_gui(const std::vector<PartitionInfo>& partitions) {

    return std::any_of(partitions.begin(), partitions.end(),

                       [](const PartitionInfo& info) { return info.requires_display; });

}



bool running_in_gui_wrapper() {

    const char* flag = std::getenv("RUNNING_IN_GUI_CONTAINER");

    return flag && *flag;

}



bool reexec_in_gui_wrapper(const std::vector<std::string>& raw_args, const std::string& wrapper) {

    std::vector<char*> argv;

    argv.reserve(raw_args.size() + 2);

    argv.push_back(const_cast<char*>(wrapper.c_str()));

    for (const auto& arg : raw_args)

        argv.push_back(const_cast<char*>(arg.c_str()));

    argv.push_back(nullptr);



    log::info("ExÃ©cution des fragments GUI via " + wrapper);

    execvp(argv[0], argv.data());

    log::error("execvp(" + wrapper + ") a Ã©chouÃ©");

    return true;

}



int run_cli(const std::vector<std::string_view>& args,
            const std::vector<std::string>& raw_args) {
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

    Diagnostics diag;

    const std::string exe_name = std::filesystem::path(std::string(args.front())).filename().string();
    const bool is_emulator = exe_name.find("emulator") != std::string::npos;
    if (is_emulator && opts.native_mode) {
        diag.error("Le binaire fragment_emulator n'exécute que l'émulation; "
                   "utiliser fragment_executor pour le natif (--native ou --native-force).");
        return 1;
    }

    if (!opts.summary_file.empty() && !opts.asm_files.empty()) {
        diag.error("Choisir soit des fichiers ASM, soit un fichier --summary, mais pas les deux.");
        return 1;
    }
    if (opts.summary_file.empty() && opts.asm_files.empty()) {
        diag.error("Aucun fichier ASM ni fichier r?sum? fourni.");
        print_usage(args.front());
        return 1;
    }

    std::ofstream program_log;
    if (!opts.log_path.empty() && !open_log_file(opts.log_path, program_log))
        diag.warning("Impossible d'ouvrir le fichier de log: " + opts.log_path);

    ExecutorConfig exec_cfg;
    exec_cfg.use_native_execution = opts.native_mode;
    FragmentExecutor executor(exec_cfg);

    ExecutionPlanData plan;
    if (!build_execution_plan(opts, args, raw_args, executor, plan, diag)) {
        set_partition_registry(nullptr);
        return 1;
    }

    ExecutionResult last_result;
    bool all_success = execute_plan(opts, executor, plan, program_log, last_result);

    set_partition_registry(nullptr);
    return all_success ? 0 : 1;
}




}  // namespace fragment

