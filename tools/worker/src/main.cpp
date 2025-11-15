#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include "worker/dynamorio_runner.hpp"
#include "worker/job_runner.hpp"
#include "worker/queue_loader.hpp"
#include "worker/reporter.hpp"

namespace {

struct CliOptions {
    std::string summary_path;
    std::vector<std::string> task_ids;
    std::string queue_file;
    std::map<std::string, uint64_t> default_inputs;
    std::string dynamo_binary;
    std::vector<std::string> dynamo_args;
    std::string runner_binary;
    std::string runner_launcher;
    bool native_mode = false;
    worker::ExecutionBackend backend = worker::ExecutionBackend::Emulator;
    worker::ConnectorMode connector = worker::ConnectorMode::Direct;
    worker::OutputFormat output = worker::OutputFormat::Text;
    std::string log_path;
    bool reset_state = false;
    std::string connector_endpoint;
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
              << "  --native           Active l'exécution native\n"
              << "  --backend backend  Choisir le backend d'exécution (emulator|dynamo)\n"
              << "  --output text|json Format de sortie (text par défaut)\n"
              << "  --reset-state      Réinitialise l'état entre chaque tâche\n"
              << "  --log <file>       Capture la sortie stdout détectée dans un fichier\n"
              << "  --drrun <binary>   Exécuter un binaire complet via DynamoRIO (docker \"dynamorio-runner\")\n"
              << "  --drrun-arg <arg>  Argument supplémentaire pour le binaire (répétable)\n"
              << "  --connector mode   Méthode de liaison backend (direct|http)\n"
              << "  --connector-endpoint <url>  Endpoint du connecteur (HTTP)\n"
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
        } else if (arg == "--native")
            opts.native_mode = true;
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
        }
        else if (arg == "--backend") {
            if (++i >= argc)
                throw std::runtime_error("--backend requiert emulator|dynamo");
            std::string backend(argv[i]);
            if (backend == "emulator")
                opts.backend = worker::ExecutionBackend::Emulator;
            else if (backend == "dynamo")
                opts.backend = worker::ExecutionBackend::Dynamo;
            else
                throw std::runtime_error("Backend inconnu: " + backend);
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
        } else if (arg == "--runner-binary") {
            if (++i >= argc)
                throw std::runtime_error("--runner-binary requiert un chemin");
            opts.runner_binary = argv[i];
        } else if (arg == "--runner-launcher") {
            if (++i >= argc)
                throw std::runtime_error("--runner-launcher requiert un chemin");
            opts.runner_launcher = argv[i];
        }
        else if (arg == "--output") {
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

    if (opts.dynamo_binary.empty()) {
        if (opts.summary_path.empty())
            throw std::runtime_error("--summary est obligatoire");
        if (opts.queue_file.empty() && opts.task_ids.empty())
            throw std::runtime_error("Aucune tâche fournie (utiliser --task ou --queue)");
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

        worker::WorkerConfig config;
        config.native_mode = opts.native_mode;
        config.executor.use_native_execution = opts.native_mode;
        config.reset_between_tasks = opts.reset_state;
        config.backend = opts.backend;
        config.connector = opts.connector;
        config.connector_endpoint = opts.connector_endpoint;
        if (!opts.runner_binary.empty())
            config.dynamo_runner_binary = opts.runner_binary;
        if (!opts.runner_launcher.empty())
            config.dynamo_launcher = opts.runner_launcher;

        worker::JobRunner runner(opts.summary_path, config);

        worker::WorkerReport report;
        report.summary_path = runner.summary_path();
        report.native_mode = opts.native_mode;

        std::ofstream log_stream;
        if (!opts.log_path.empty())
            log_stream.open(opts.log_path, std::ios::out | std::ios::trunc);

        for (const auto& task : tasks) {
            try {
                auto task_report = runner.execute(task);
                if (log_stream && !task_report.result.program_stdout.empty())
                    log_stream << task_report.result.program_stdout;
                report.tasks.push_back(std::move(task_report));
            } catch (const std::exception& e) {
                worker::TaskReport failure;
                failure.partition_id = task.partition_id;
                failure.inputs = task.inputs;
                failure.result.success = false;
                failure.result.error_message = e.what();
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
