#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "worker/job_runner.hpp"
#include "worker/queue_loader.hpp"
#include "worker/reporter.hpp"

namespace {

struct CliOptions {
    std::string summary_path;
    std::vector<std::string> task_ids;
    std::string queue_file;
    std::map<std::string, uint64_t> default_inputs;
    bool native_mode = false;
    worker::OutputFormat output = worker::OutputFormat::Text;
    std::string log_path;
    bool reset_state = false;
};

void print_usage(const char* prog) {
    std::cout << "Usage:\n"
              << "  " << prog << " --summary summary.json --task func_3_main [--input rax=0x1]\n"
              << "  " << prog << " --summary summary.json --queue queue.txt [--output json]\n\n"
              << "Options:\n"
              << "  --summary <path>   Summary JSON généré par splitter (obligatoire)\n"
              << "  --task <id>        Identifier de partition à exécuter (répétable)\n"
              << "  --queue <file>     Fichier listant les tâches (\"partition reg=val ...\")\n"
              << "  --input reg=val    Valeur par défaut pour les tâches ajoutées via --task\n"
              << "  --native           Active l'exécution native\n"
              << "  --output text|json Format de sortie (text par défaut)\n"
              << "  --reset-state      Réinitialise l'état entre chaque tâche\n"
              << "  --log <file>       Capture la sortie stdout détectée dans un fichier\n"
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

    if (opts.summary_path.empty())
        throw std::runtime_error("--summary est obligatoire");

    if (opts.queue_file.empty() && opts.task_ids.empty())
        throw std::runtime_error("Aucune tâche fournie (utiliser --task ou --queue)");

    return opts;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const CliOptions opts = parse_cli(argc, argv);

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
        return all_ok ? 0 : 1;
    } catch (const std::exception& e) {
        std::cerr << "Erreur worker: " << e.what() << "\n";
        return 1;
    }
}
