#include "cli/Cli.hpp"

#include "support/Logging.hpp"
#include "support/StructuredRunLogger.hpp"

#include "runtime/Runner.hpp"



#include <algorithm>
#include <cctype>
#include <chrono>

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

static std::string lower_copy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

static AbiProfile select_abi_profile(const PartitionSummary& summary) {
    const std::string os = lower_copy(summary.binary_os);
    const std::string format = lower_copy(summary.binary_format);
    if (os == "windows" && format == "pe")
        return AbiProfile::WindowsX64;
    return AbiProfile::SystemV;
}

static std::string json_bool(bool value) {
    return value ? "true" : "false";
}

static std::string current_backend_name(bool native_mode) {
    return native_mode ? "native" : "emulated";
}

static std::string build_error_payload(const std::string& message) {
    std::ostringstream payload;
    payload << R"({"error":)" << log::StructuredRunLogger::QuoteForJson(message) << "}";
    return payload.str();
}

static void emit_partition_loaded(log::StructuredRunLogger& structured_log,
                                  const ExecutionEntry& entry,
                                  std::size_t index,
                                  std::size_t total,
                                  const std::string& source) {
    std::ostringstream payload;
    payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
            << R"(,"asm_path":)" << log::StructuredRunLogger::QuoteForJson(entry.asm_path)
            << R"(,"binary_path":)" << log::StructuredRunLogger::QuoteForJson(derive_binary_path(entry))
            << R"(,"index":)" << index
            << R"(,"total":)" << total
            << R"(,"source":)" << log::StructuredRunLogger::QuoteForJson(source)
            << R"(,"has_metadata":)" << json_bool(entry.meta.has_value()) << "}";
    structured_log.info("partition_loaded", "Partition loaded into execution plan", payload.str());
}

static bool build_execution_plan(const CliOptions& opts,
                                const std::vector<std::string_view>& args,
                                const std::vector<std::string>& raw_args,
                                FragmentExecutor& executor,
                                ExecutionPlanData& plan,
                                Diagnostics& diag,
                                log::StructuredRunLogger& structured_log) {
    if (!opts.summary_file.empty()) {
        PartitionSummary summary;
        try {
            summary = load_partition_summary(opts.summary_file, opts.skip_memory_check);
        } catch (const std::exception& e) {
            const std::string error = std::string("Erreur lors du chargement du graphe: ") + e.what();
            diag.error(error);
            structured_log.error("partition_load_error", "Failed to load summary graph", build_error_payload(error));
            return false;
        }

        const AbiProfile profile = select_abi_profile(summary);
        executor.set_abi_profile(profile);
        log::info("ABI profile selected: " + abi_profile_name(profile)
                  + " (binary_os=" + summary.binary_os + ", binary_format=" + summary.binary_format + ")");

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
                if (reexec_in_gui_wrapper(raw_args, wrapper_path)) {
                    structured_log.info(
                        "gui_wrapper_reexec",
                        "Re-executed through GUI wrapper",
                        std::string(R"({"wrapper":)")
                            + log::StructuredRunLogger::QuoteForJson(wrapper_path) + "}");
                    return false;
                }
            } else {
                diag.warning("Fragments GUI d?tect?s mais aucun wrapper GUI n'est disponible.");
                structured_log.warning(
                    "gui_wrapper_missing",
                    "GUI fragments detected without wrapper",
                    std::string(R"({"summary":)")
                        + log::StructuredRunLogger::QuoteForJson(opts.summary_file) + "}");
            }
        }

        set_partition_registry(&plan.partitions);
        try {
            plan.entries = plan_from_summary(plan.partitions, plan.expected_inputs);
        } catch (const std::exception& e) {
            const std::string error = std::string("Cycle d?tect? dans le graphe: ") + e.what();
            diag.error(error);
            structured_log.error("partition_graph_cycle", "Cycle detected in partition graph", build_error_payload(error));
            return false;
        }

        if (!summary.binary_path.empty())
            executor.set_binary_path(summary.binary_path);
        preload_initial_memory(summary, executor);
        if (opts.native_mode)
            ensure_required_libraries(summary);
        print_plan_overview(opts.summary_file, plan.entries);
        for (std::size_t idx = 0; idx < plan.entries.size(); ++idx)
            emit_partition_loaded(structured_log, plan.entries[idx], idx, plan.entries.size(), "summary");
        return true;
    }

    set_partition_registry(nullptr);
    executor.set_abi_profile(AbiProfile::SystemV);
    log::info("ABI profile selected: " + abi_profile_name(AbiProfile::SystemV)
              + " (no summary metadata)");
    plan.entries = plan_from_files(opts.asm_files);
    plan.from_summary = false;
    for (std::size_t idx = 0; idx < plan.entries.size(); ++idx)
        emit_partition_loaded(structured_log, plan.entries[idx], idx, plan.entries.size(), "asm");
    return true;
}

static bool execute_plan(const CliOptions& opts,
                         FragmentExecutor& executor,
                         const ExecutionPlanData& plan,
                         std::ofstream& program_log,
                         ExecutionResult& last_result,
                         log::StructuredRunLogger& structured_log) {
    log::banner();
    apply_inputs(executor, opts.inputs);

    log::section("?tat initial des registres");
    executor.print_register_state();

    std::set<std::string> consumed_external_inputs;
    bool all_success = true;

    for (size_t idx = 0; idx < plan.entries.size(); ++idx) {
        const auto& entry = plan.entries[idx];
        const auto entry_start = std::chrono::steady_clock::now();

        describe_entry(idx, entry);
        bool missing_inputs = prepare_external_inputs(entry, executor, opts.inputs, consumed_external_inputs);

        {
            std::ostringstream payload;
            payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
                    << R"(,"backend":)"
                    << log::StructuredRunLogger::QuoteForJson(current_backend_name(opts.native_mode))
                    << R"(,"native_mode":)" << json_bool(opts.native_mode)
                    << R"(,"force_native":)" << json_bool(opts.force_native) << "}";
            structured_log.info("backend_selected", "Execution backend selected", payload.str());
        }

        {
            std::ostringstream payload;
            payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
                    << R"(,"asm_path":)" << log::StructuredRunLogger::QuoteForJson(entry.asm_path)
                    << R"(,"binary_path":)" << log::StructuredRunLogger::QuoteForJson(derive_binary_path(entry))
                    << R"(,"index":)" << idx
                    << R"(,"total":)" << plan.entries.size()
                    << R"(,"mode":)"
                    << log::StructuredRunLogger::QuoteForJson(current_backend_name(opts.native_mode)) << "}";
            structured_log.info("execution_started", "Fragment execution started", payload.str());
        }

        bool has_external_calls = entry.meta && (!entry.meta->get().external_calls.empty() ||
                                                 !entry.meta->get().unresolved_calls.empty());
        if (opts.native_mode && missing_inputs && !opts.force_native) {
            last_result.success = false;
            last_result.error_message = "Ex?cution native bloqu?e: entr?es externes manquantes pour " + entry.name;
            log::error(last_result.error_message);
            structured_log.error(
                "execution_error",
                "Native execution blocked due to missing external inputs",
                std::string(R"({"partition":)")
                    + log::StructuredRunLogger::QuoteForJson(entry.name)
                    + R"(,"error":)" + log::StructuredRunLogger::QuoteForJson(last_result.error_message) + "}");
            all_success = false;
            break;
        }

        if (opts.native_mode && has_external_calls) {
            const std::string risk = missing_inputs
                ? "entr?es externes manquantes et appels externes/non r?solus"
                : "appels externes/non r?solus";
            log::warning("Ex?cution native malgr? " + risk + " sur " + entry.name
                         + " (pas de repli, risque de crash)." );
            structured_log.warning(
                "external_calls_detected",
                "Native execution with unresolved external calls",
                std::string(R"({"partition":)")
                    + log::StructuredRunLogger::QuoteForJson(entry.name)
                    + R"(,"risk":)" + log::StructuredRunLogger::QuoteForJson(risk) + "}");
        }

        if (!execute_entry(entry, opts.native_mode, opts.force_native, executor, last_result)) {
            const auto duration_ms =
                std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - entry_start)
                    .count();
            std::ostringstream payload;
            payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
                    << R"(,"duration_ms":)" << duration_ms
                    << R"(,"error":)" << log::StructuredRunLogger::QuoteForJson(last_result.error_message) << "}";
            structured_log.error("execution_failed", "Fragment backend run failed", payload.str());
            all_success = false;
            break;
        }

        log::section("R?sultats");
        last_result.print();
        log_program_output(program_log, last_result);

        const auto duration_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - entry_start)
                .count();
        {
            std::ostringstream payload;
            payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
                    << R"(,"success":)" << json_bool(last_result.success)
                    << R"(,"duration_ms":)" << duration_ms
                    << R"(,"instructions":)" << last_result.instructions_executed
                    << R"(,"memory_accesses":)" << last_result.memory_accesses << "}";
            structured_log.info("execution_completed", "Fragment execution completed", payload.str());
        }

        {
            std::ostringstream payload;
            payload << R"({"partition":)" << log::StructuredRunLogger::QuoteForJson(entry.name)
                    << R"(,"stdout_bytes":)" << last_result.program_stdout.size()
                    << R"(,"stderr_bytes":)" << last_result.program_stderr.size()
                    << R"(,"fd_captures":)" << last_result.fd_outputs.size() << "}";
            structured_log.info("output_summary", "Captured stdout/stderr summary", payload.str());
        }

        if (!last_result.success) {
            all_success = false;
            log::error("Arr?t: ?chec de l'ex?cution pour " + entry.asm_path);
            structured_log.error(
                "execution_error",
                "Fragment execution marked as failed",
                std::string(R"({"partition":)")
                    + log::StructuredRunLogger::QuoteForJson(entry.name)
                    + R"(,"error":)" + log::StructuredRunLogger::QuoteForJson(last_result.error_message) + "}");
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
    const auto run_start = std::chrono::steady_clock::now();
    auto complete_run = [&](log::StructuredRunLogger& structured_log, int exit_code) -> int {
        const auto run_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - run_start)
                .count();
        std::ostringstream payload;
        payload << R"({"exit_code":)" << exit_code
                << R"(,"duration_ms":)" << run_ms << "}";
        if (exit_code == 0)
            structured_log.info("run_completed", "Executor run completed", payload.str());
        else
            structured_log.error("run_completed", "Executor run failed", payload.str());
        return exit_code;
    };

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

    const std::string structured_log_path =
        opts.structured_log_path.empty() ? log::StructuredRunLogger::DefaultLogPath() : opts.structured_log_path;
    log::StructuredRunLogger structured_log(structured_log_path);
    if (structured_log.enabled())
        log::info("Structured log file: " + structured_log.path());
    else
        log::warning("Unable to open structured log file: " + structured_log_path);

    {
        std::ostringstream payload;
        payload << R"({"argv0":)"
                << log::StructuredRunLogger::QuoteForJson(args.empty() ? "fragment_executor" : std::string(args.front()))
                << R"(,"native_mode":)" << json_bool(opts.native_mode)
                << R"(,"force_native":)" << json_bool(opts.force_native)
                << R"(,"summary":)" << log::StructuredRunLogger::QuoteForJson(opts.summary_file)
                << R"(,"asm_count":)" << opts.asm_files.size()
                << R"(,"text_log":)" << log::StructuredRunLogger::QuoteForJson(opts.log_path)
                << R"(,"structured_log":)" << log::StructuredRunLogger::QuoteForJson(structured_log_path) << "}";
        structured_log.info("run_started", "Executor run started", payload.str());
    }

    Diagnostics diag;

    const std::string exe_name = std::filesystem::path(std::string(args.front())).filename().string();
    const bool is_emulator = exe_name.find("emulator") != std::string::npos;
    if (is_emulator && opts.native_mode) {
        diag.error("Le binaire fragment_emulator n'exécute que l'émulation; "
                   "utiliser fragment_executor pour le natif (--native ou --native-force).");
        structured_log.error(
            "argument_error",
            "Invalid native mode on emulator binary",
            R"({"error":"native mode requested on fragment_emulator"})");
        return complete_run(structured_log, 1);
    }

    if (!opts.summary_file.empty() && !opts.asm_files.empty()) {
        diag.error("Choisir soit des fichiers ASM, soit un fichier --summary, mais pas les deux.");
        structured_log.error("argument_error",
                             "Summary and ASM files provided together",
                             R"({"error":"conflicting inputs"})");
        return complete_run(structured_log, 1);
    }
    if (opts.summary_file.empty() && opts.asm_files.empty()) {
        diag.error("Aucun fichier ASM ni fichier r?sum? fourni.");
        print_usage(args.front());
        structured_log.error("argument_error", "No input file provided", R"({"error":"missing summary or asm"})");
        return complete_run(structured_log, 1);
    }

    std::ofstream program_log;
    if (!opts.log_path.empty() && !open_log_file(opts.log_path, program_log))
        diag.warning("Impossible d'ouvrir le fichier de log: " + opts.log_path);

    ExecutorConfig exec_cfg;
    exec_cfg.use_native_execution = opts.native_mode;
    FragmentExecutor executor(exec_cfg);

    ExecutionPlanData plan;
    if (!build_execution_plan(opts, args, raw_args, executor, plan, diag, structured_log)) {
        set_partition_registry(nullptr);
        return complete_run(structured_log, 1);
    }

    ExecutionResult last_result;
    bool all_success = execute_plan(opts, executor, plan, program_log, last_result, structured_log);

    set_partition_registry(nullptr);
    return complete_run(structured_log, all_success ? 0 : 1);
}




}  // namespace fragment

