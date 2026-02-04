#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <unistd.h>
#include <stdexcept>
#include <string>
#include <vector>

#include "core/Config.hpp"
#include "worker/runtime/DynamoRunner.hpp"
#include "worker/runtime/JobRunner.hpp"
#include "worker/io/QueueLoader.hpp"
#include "worker/io/Reporter.hpp"
#include "partition/PartitionSummary.hpp"

namespace {

struct CliOptions {
    std::string summary_path;
    std::vector<std::string> task_ids;
    std::string queue_file;
    worker::RegisterState default_inputs;
    std::string dynamo_binary;
    std::vector<std::string> dynamo_args;
    std::string runner_binary;
    std::string runner_launcher;
    worker::ExecutionMode mode = worker::ExecutionMode::Auto;
    worker::ConnectorMode connector = worker::ConnectorMode::Direct;
    worker::OutputFormat output = worker::OutputFormat::Text;
    std::string log_path;
    bool reset_state = false;
    std::string connector_endpoint;
    bool capture_stdout = true;
    bool capture_stderr = true;
    std::string stdin_text;
    std::string stdin_file;
    std::vector<fragment::FdRule> extra_fds;
    std::string linux_fragments_policy;
    std::string windows_fragments_policy;
    bool linux_fragments_set = false;
    bool windows_fragments_set = false;
    bool wsl_enabled = false;
    bool wsl_enabled_set = false;
    double wsl_min_reward = 0.0;
    bool wsl_min_reward_set = false;
    std::uint64_t wsl_min_jobs = 0;
    bool wsl_min_jobs_set = false;
    double wsl_current_reward = 0.0;
    bool wsl_current_reward_set = false;
    std::uint64_t wsl_available_jobs = 0;
    bool wsl_available_jobs_set = false;
};

void print_usage(const char* prog) {
    std::cout << "Usage:\n"
              << "  " << prog << " --summary summary.json --task func_3_main [--input rax=0x1]\n"
              << "  " << prog << " --summary summary.json --queue queue.txt [--output json]\n"
              << "  " << prog << " --drrun /path/to/binaire [--drrun-arg arg]\n\n"
              << "Options:\n"
              << "  --summary <path>   Summary JSON généré par splitter (obligatoire)\n"
              << "  --task <id>        Identifier de partition à exécuter (répétable)\n"
              << "  --queue <file>     Fichier listant les tâches (\"partition reg=val ...\")\n"
              << "  --input reg=val    Valeur par défaut pour les tâches ajoutées via --task\n"
              << "  --mode auto|emu|native|dynamo  Choix du backend (priorité: dynamo > native > emu en auto)\n"
              << "  --output text|json Format de sortie (text par défaut)\n"
              << "  --reset-state      Réinitialise l'état entre chaque tâche\n"
              << "  --log <file>       Capture la sortie stdout détectée dans un fichier\n"
              << "  --no-capture-stdout  Ne capture pas stdout du fragment (passe direct)\n"
              << "  --no-capture-stderr  Ne capture pas stderr du fragment (passe direct)\n"
              << "  --stdin-text <s>   Fournit cette chaîne sur stdin du fragment\n"
              << "  --stdin-file <p>   Lit stdin du fragment depuis ce fichier\n"
              << "  --fd-capture <fd>  Capture les écritures sur ce descripteur (répétable)\n"
              << "  --drrun <binary>   Exécuter un binaire complet via DynamoRIO (docker \"dynamorio-runner\")\n"
              << "  --drrun-arg <arg>  Argument supplémentaire pour le binaire (répétable)\n"
              << "  --connector mode   Méthode de liaison backend (direct|http)\n"
              << "  --connector-endpoint <url>  Endpoint du connecteur (HTTP)\n"
              << "  --linux-fragments native|wsl|skip|error|queue  Politique fragments Linux\n"
              << "  --windows-fragments native|wsl|skip|error|queue  Politique fragments Windows\n"
              << "  --wsl-enable        Active la délégation WSL (si conditions remplies)\n"
              << "  --wsl-disable       Désactive la délégation WSL\n"
              << "  --wsl-min-reward <v>  Seuil de récompense minimal\n"
              << "  --wsl-min-jobs <n>  Seuil minimal de jobs disponibles\n"
              << "  --wsl-reward <v>    Récompense actuelle (entrée trigger)\n"
              << "  --wsl-available-jobs <n> Jobs disponibles (entrée trigger)\n"
              << "  --runner-binary <path> Binaire runner (backend Dynamo)\n"
              << "  --runner-launcher <path> Script/commande pour lancer le runner Dynamo\n"
              << "  --help             Affiche cette aide\n";
}

CliOptions parse_cli(int argc, char** argv) {
    CliOptions opts;
    if (argc <= 1)
        throw std::runtime_error("Arguments manquants (utiliser --help)");

    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--summary") {
            if (++i >= argc)
                throw std::runtime_error("--summary requiert un chemin");
            opts.summary_path = argv[i];
        } else if (arg == "--task") {
            if (++i >= argc)
                throw std::runtime_error("--task requiert un identifiant");
            opts.task_ids.emplace_back(argv[i]);
        } else if (arg == "--queue") {
            if (++i >= argc)
                throw std::runtime_error("--queue requiert un fichier");
            opts.queue_file = argv[i];
        } else if (arg == "--input") {
            if (++i >= argc)
                throw std::runtime_error("--input requiert reg=val");
            const std::string token(argv[i]);
            const auto pos = token.find('=');
            if (pos == std::string::npos)
                throw std::runtime_error("Argument --input invalide: " + token);
            const std::string reg = token.substr(0, pos);
            const std::string value = token.substr(pos + 1);
            opts.default_inputs[reg] = worker::parse_register_value(value);
        } else if (arg == "--mode") {
            if (++i >= argc)
                throw std::runtime_error("--mode requiert auto|emu|native|dynamo");
            std::string mode(argv[i]);
            if (mode == "auto")
                opts.mode = worker::ExecutionMode::Auto;
            else if (mode == "emu")
                opts.mode = worker::ExecutionMode::Emulator;
            else if (mode == "native")
                opts.mode = worker::ExecutionMode::Native;
            else if (mode == "dynamo")
                opts.mode = worker::ExecutionMode::Dynamo;
            else
                throw std::runtime_error("Mode inconnu: " + mode);
        }
        else if (arg == "--reset-state")
            opts.reset_state = true;
        else if (arg == "--drrun") {
            if (++i >= argc)
                throw std::runtime_error("--drrun requiert un chemin vers un binaire");
            opts.dynamo_binary = argv[i];
        } else if (arg == "--drrun-arg") {
            if (++i >= argc)
                throw std::runtime_error("--drrun-arg requiert une valeur");
            opts.dynamo_args.emplace_back(argv[i]);
        } else if (arg == "--connector") {
            if (++i >= argc)
                throw std::runtime_error("--connector requiert direct|http");
            std::string mode(argv[i]);
            if (mode == "direct")
                opts.connector = worker::ConnectorMode::Direct;
            else if (mode == "http")
                opts.connector = worker::ConnectorMode::Http;
            else
                throw std::runtime_error("Connecteur inconnu: " + mode);
        } else if (arg == "--connector-endpoint") {
            if (++i >= argc)
                throw std::runtime_error("--connector-endpoint requiert une valeur");
            opts.connector_endpoint = argv[i];
        } else if (arg == "--linux-fragments") {
            if (++i >= argc)
                throw std::runtime_error("--linux-fragments requiert une valeur");
            opts.linux_fragments_policy = argv[i];
            opts.linux_fragments_set = true;
        } else if (arg == "--windows-fragments") {
            if (++i >= argc)
                throw std::runtime_error("--windows-fragments requiert une valeur");
            opts.windows_fragments_policy = argv[i];
            opts.windows_fragments_set = true;
        } else if (arg == "--wsl-enable") {
            opts.wsl_enabled = true;
            opts.wsl_enabled_set = true;
        } else if (arg == "--wsl-disable") {
            opts.wsl_enabled = false;
            opts.wsl_enabled_set = true;
        } else if (arg == "--wsl-min-reward") {
            if (++i >= argc)
                throw std::runtime_error("--wsl-min-reward requiert une valeur");
            opts.wsl_min_reward = std::stod(argv[i]);
            opts.wsl_min_reward_set = true;
        } else if (arg == "--wsl-min-jobs") {
            if (++i >= argc)
                throw std::runtime_error("--wsl-min-jobs requiert une valeur");
            opts.wsl_min_jobs = std::stoull(argv[i]);
            opts.wsl_min_jobs_set = true;
        } else if (arg == "--wsl-reward") {
            if (++i >= argc)
                throw std::runtime_error("--wsl-reward requiert une valeur");
            opts.wsl_current_reward = std::stod(argv[i]);
            opts.wsl_current_reward_set = true;
        } else if (arg == "--wsl-available-jobs") {
            if (++i >= argc)
                throw std::runtime_error("--wsl-available-jobs requiert une valeur");
            opts.wsl_available_jobs = std::stoull(argv[i]);
            opts.wsl_available_jobs_set = true;
        } else if (arg == "--runner-binary") {
            if (++i >= argc)
                throw std::runtime_error("--runner-binary requiert un chemin");
            opts.runner_binary = argv[i];
        } else if (arg == "--runner-launcher") {
            if (++i >= argc)
                throw std::runtime_error("--runner-launcher requiert un chemin");
            opts.runner_launcher = argv[i];
        } else if (arg == "--no-capture-stdout") {
            opts.capture_stdout = false;
        } else if (arg == "--no-capture-stderr") {
            opts.capture_stderr = false;
        } else if (arg == "--stdin-text") {
            if (++i >= argc)
                throw std::runtime_error("--stdin-text requiert une chaîne");
            opts.stdin_text = argv[i];
        } else if (arg == "--stdin-file") {
            if (++i >= argc)
                throw std::runtime_error("--stdin-file requiert un chemin");
            opts.stdin_file = argv[i];
        } else if (arg == "--fd-capture") {
            if (++i >= argc)
                throw std::runtime_error("--fd-capture requiert un FD");
            int fd = std::stoi(argv[i]);
            fragment::FdRule redir;
            redir.fd = fd;
            redir.capture = true;
            opts.extra_fds.push_back(std::move(redir));
        } else if (arg == "--output") {
            if (++i >= argc)
                throw std::runtime_error("--output requiert text|json");
            std::string mode(argv[i]);
            if (mode == "json")
                opts.output = worker::OutputFormat::Json;
            else if (mode == "text")
                opts.output = worker::OutputFormat::Text;
            else
                throw std::runtime_error("Format de sortie inconnu: " + mode);
        } else if (arg == "--log") {
            if (++i >= argc)
                throw std::runtime_error("--log requiert un fichier");
            opts.log_path = argv[i];
        } else if (arg == "--help") {
            print_usage(argv[0]);
            std::exit(0);
        } else
            throw std::runtime_error("Option inconnue: " + arg);
    }

    if (opts.dynamo_binary.empty() && opts.summary_path.empty())
        throw std::runtime_error("--summary est obligatoire");
    if (!opts.stdin_text.empty() && !opts.stdin_file.empty())
        throw std::runtime_error("--stdin-text et --stdin-file sont exclusifs");

    if (!opts.linux_fragments_set) {
        if (const char* env = std::getenv("SILICIUM_LINUX_FRAGMENTS")) {
            opts.linux_fragments_policy = env;
            opts.linux_fragments_set = true;
        }
    }
    if (!opts.windows_fragments_set) {
        if (const char* env = std::getenv("SILICIUM_WINDOWS_FRAGMENTS")) {
            opts.windows_fragments_policy = env;
            opts.windows_fragments_set = true;
        }
    }
    if (!opts.wsl_enabled_set) {
        if (const char* env = std::getenv("SILICIUM_WSL_ENABLE")) {
            std::string value(env);
            if (value == "1" || value == "true" || value == "yes") {
                opts.wsl_enabled = true;
                opts.wsl_enabled_set = true;
            } else if (value == "0" || value == "false" || value == "no") {
                opts.wsl_enabled = false;
                opts.wsl_enabled_set = true;
            }
        }
    }
    if (!opts.wsl_min_reward_set) {
        if (const char* env = std::getenv("SILICIUM_WSL_MIN_REWARD")) {
            opts.wsl_min_reward = std::stod(env);
            opts.wsl_min_reward_set = true;
        }
    }
    if (!opts.wsl_min_jobs_set) {
        if (const char* env = std::getenv("SILICIUM_WSL_MIN_JOBS")) {
            opts.wsl_min_jobs = std::stoull(env);
            opts.wsl_min_jobs_set = true;
        }
    }
    if (!opts.wsl_current_reward_set) {
        if (const char* env = std::getenv("SILICIUM_WSL_REWARD")) {
            opts.wsl_current_reward = std::stod(env);
            opts.wsl_current_reward_set = true;
        }
    }
    if (!opts.wsl_available_jobs_set) {
        if (const char* env = std::getenv("SILICIUM_WSL_AVAILABLE_JOBS")) {
            opts.wsl_available_jobs = std::stoull(env);
            opts.wsl_available_jobs_set = true;
        }
    }

    return opts;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const CliOptions opts = parse_cli(argc, argv);

        if (!opts.dynamo_binary.empty()) {
            worker::DynamoRunner dyn_runner;
            std::string dyn_stdout;
            std::string dyn_stderr;
            const bool ok = dyn_runner.run_binary(opts.dynamo_binary,
                                                  opts.dynamo_args,
                                                  dyn_stdout,
                                                  dyn_stderr);
            if (!dyn_stdout.empty())
                std::cout << dyn_stdout;
            if (!dyn_stderr.empty())
                std::cerr << dyn_stderr << "\n";
            return !ok;
        }

        std::vector<worker::Task> tasks;
        if (!opts.queue_file.empty()) {
            auto queued = worker::load_queue_file(opts.queue_file);
            tasks.insert(tasks.end(), queued.begin(), queued.end());
        }
        for (const auto& id : opts.task_ids) {
            worker::Task t;
            t.partition_id = id;
            t.inputs = opts.default_inputs;
            tasks.push_back(std::move(t));
        }
        if (tasks.empty()) {
            fragment::PartitionSummary summary = fragment::load_partition_summary(opts.summary_path);
            auto ordered = fragment::order_partitions(summary.partitions);
            for (const auto& id : ordered) {
                worker::Task t;
                t.partition_id = id;
                t.inputs = opts.default_inputs;
                tasks.push_back(std::move(t));
            }
        }

        worker::WorkerConfig config;
        config.mode = opts.mode;
        config.reset_between_tasks = opts.reset_state;
        config.connector = opts.connector;
        config.connector_endpoint = opts.connector_endpoint;
        if (opts.linux_fragments_set)
            config.fragment_os_policy.linux = worker::parse_fragment_os_action(opts.linux_fragments_policy);
        if (opts.windows_fragments_set)
            config.fragment_os_policy.windows = worker::parse_fragment_os_action(opts.windows_fragments_policy);
        config.wsl_triggers.enabled = opts.wsl_enabled_set ? opts.wsl_enabled : false;
        if (opts.wsl_min_reward_set)
            config.wsl_triggers.min_reward = opts.wsl_min_reward;
        if (opts.wsl_min_jobs_set)
            config.wsl_triggers.min_jobs = opts.wsl_min_jobs;
        if (opts.wsl_current_reward_set)
            config.wsl_triggers.current_reward = opts.wsl_current_reward;
        if (opts.wsl_available_jobs_set)
            config.wsl_triggers.available_jobs = opts.wsl_available_jobs;
        config.wsl_enabled = worker::evaluate_wsl_triggers(config.wsl_triggers, &config.wsl_decision);
        if (!opts.runner_binary.empty())
            config.dynamo_runner_binary = opts.runner_binary;
        if (!opts.runner_launcher.empty())
            config.dynamo_launcher = opts.runner_launcher;
        std::vector<fragment::FdRule> fd_rules;
        fragment::FdRule stdin_rule;
        stdin_rule.fd = STDIN_FILENO;
        stdin_rule.alias = "stdin";
        if (!opts.stdin_file.empty()) {
            std::ifstream in(opts.stdin_file, std::ios::binary);
            if (!in)
                throw std::runtime_error("Impossible de lire --stdin-file: " + opts.stdin_file);
            std::ostringstream ss;
            ss << in.rdbuf();
            stdin_rule.input_data = ss.str();
        } else {
            stdin_rule.input_data = opts.stdin_text;
        }
        fd_rules.push_back(std::move(stdin_rule));

        fragment::FdRule stdout_rule;
        stdout_rule.fd = STDOUT_FILENO;
        stdout_rule.capture = opts.capture_stdout;
        stdout_rule.alias = "stdout";
        fd_rules.push_back(stdout_rule);

        fragment::FdRule stderr_rule;
        stderr_rule.fd = STDERR_FILENO;
        stderr_rule.capture = opts.capture_stderr;
        stderr_rule.alias = "stderr";
        fd_rules.push_back(stderr_rule);

        fd_rules.insert(fd_rules.end(), opts.extra_fds.begin(), opts.extra_fds.end());
        config.executor.fd_rules = std::move(fd_rules);

        worker::JobRunner runner(opts.summary_path, config);

        worker::WorkerReport report;
        report.summary_path = runner.summary_path();
        report.mode = opts.mode;

        std::ofstream log_stream;
        if (!opts.log_path.empty())
            log_stream.open(opts.log_path, std::ios::out | std::ios::trunc);

        for (const auto& task : tasks) {
            try {
                auto task_report = runner.execute(task);
                if (log_stream) {
                    if (!task_report.result.program_stdout.empty())
                        log_stream << task_report.result.program_stdout;
                    if (!task_report.result.program_stderr.empty())
                        log_stream << task_report.result.program_stderr;
                }
                report.tasks.push_back(std::move(task_report));
            } catch (const std::exception& e) {
                worker::TaskReport failure;
                failure.partition_id = task.partition_id;
                failure.inputs = task.inputs;
                failure.result.success = false;
                failure.result.error_message = e.what();
                failure.telemetry.task_id = task.partition_id;
                failure.telemetry.type = task.type;
                failure.telemetry.status = "failure";
                failure.telemetry.linux_policy = worker::fragment_os_action_to_string(config.fragment_os_policy.linux);
                failure.telemetry.windows_policy = worker::fragment_os_action_to_string(config.fragment_os_policy.windows);
                failure.telemetry.wsl_enabled = config.wsl_enabled;
                failure.telemetry.wsl_decision = config.wsl_decision;
                report.tasks.push_back(std::move(failure));
            }
        }

        worker::Reporter reporter(opts.output, std::cout);
        reporter.emit(report);

        const bool all_ok = std::all_of(report.tasks.begin(),
                                        report.tasks.end(),
                                        [](const worker::TaskReport& task) {
                                            return task.result.success;
                                        });
        return !all_ok;
    } catch (const std::exception& e) {
        std::cerr << "Erreur worker: " << e.what() << "\n";
        return 1;
    }
}
