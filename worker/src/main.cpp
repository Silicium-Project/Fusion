#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>
#include <unistd.h>

#include "core/Config.hpp"
#include "worker/runtime/DynamoRunner.hpp"
#include "worker/runtime/JobRunner.hpp"
#include "worker/io/QueueLoader.hpp"
#include "worker/io/Reporter.hpp"
#include "worker/mcp/McpReadOnlyConnectorAdapter.hpp"
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
    bool mcp_read_only = false;
    bool mcp_read_only_set = false;
    bool mcp_enable_tools = false;
    bool mcp_enable_tools_set = false;
    std::string mcp_export_dir;
    bool cap_native = false;
    bool cap_native_set = false;
    bool cap_docker = false;
    bool cap_docker_set = false;
    bool cap_wsl = false;
    bool cap_wsl_set = false;
    bool cap_http = false;
    bool cap_http_set = false;
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
              << "  --mcp-readonly      Active l'adapter MCP read-only (resources uniquement)\n"
              << "  --mcp-enable-tools  Active les tools MCP de controle (guarded)\n"
              << "  --mcp-export-dir <path> Exporte les resources MCP dans ce dossier\n"
              << "  --cap-native on|off  Force la capacite backend native\n"
              << "  --cap-docker on|off  Force la capacite backend docker\n"
              << "  --cap-wsl on|off     Force la capacite backend WSL\n"
              << "  --cap-http on|off    Force la capacite backend HTTP\n"
              << "  --runner-binary <path> Binaire runner (backend Dynamo)\n"
              << "  --runner-launcher <path> Script/commande pour lancer le runner Dynamo\n"
              << "  --help             Affiche cette aide\n";
}

bool parse_bool_value(const std::string& value, bool* out) {
    if (value == "1" || value == "true" || value == "on" || value == "yes") {
        *out = true;
        return true;
    }
    if (value == "0" || value == "false" || value == "off" || value == "no") {
        *out = false;
        return true;
    }
    return false;
}

bool command_available(const char* command) {
#ifdef _WIN32
    const std::string cmd = std::string("where ") + command + " >NUL 2>NUL";
#else
    const std::string cmd = std::string("command -v ") + command + " >/dev/null 2>&1";
#endif
    return std::system(cmd.c_str()) == 0;
}

void apply_capability_override(bool is_set,
                               bool value,
                               bool* target) {
    if (is_set)
        *target = value;
}

void apply_capability_env_override(const char* env_name,
                                   bool* target) {
    if (const char* value = std::getenv(env_name)) {
        bool parsed = false;
        if (parse_bool_value(value, &parsed))
            *target = parsed;
    }
}

worker::BackendCapabilities detect_backend_capabilities(const CliOptions& opts) {
    worker::BackendCapabilities capabilities;
    capabilities.native = (opts.connector == worker::ConnectorMode::Direct);
    capabilities.docker = command_available("docker");
#ifdef _WIN32
    capabilities.wsl = command_available("wsl.exe") || command_available("wsl");
#else
    capabilities.wsl = false;
#endif
    capabilities.http = command_available("curl");
    if (opts.connector == worker::ConnectorMode::Http && opts.connector_endpoint.empty())
        capabilities.http = false;

    apply_capability_override(opts.cap_native_set, opts.cap_native, &capabilities.native);
    apply_capability_override(opts.cap_docker_set, opts.cap_docker, &capabilities.docker);
    apply_capability_override(opts.cap_wsl_set, opts.cap_wsl, &capabilities.wsl);
    apply_capability_override(opts.cap_http_set, opts.cap_http, &capabilities.http);

    apply_capability_env_override("SILICIUM_CAP_NATIVE", &capabilities.native);
    apply_capability_env_override("SILICIUM_CAP_DOCKER", &capabilities.docker);
    apply_capability_env_override("SILICIUM_CAP_WSL", &capabilities.wsl);
    apply_capability_env_override("SILICIUM_CAP_HTTP", &capabilities.http);
    return capabilities;
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
        } else if (arg == "--mcp-readonly") {
            opts.mcp_read_only = true;
            opts.mcp_read_only_set = true;
        } else if (arg == "--mcp-enable-tools") {
            opts.mcp_enable_tools = true;
            opts.mcp_enable_tools_set = true;
            opts.mcp_read_only = true;
            opts.mcp_read_only_set = true;
        } else if (arg == "--mcp-export-dir") {
            if (++i >= argc)
                throw std::runtime_error("--mcp-export-dir requiert un chemin");
            opts.mcp_export_dir = argv[i];
            opts.mcp_read_only = true;
            opts.mcp_read_only_set = true;
        } else if (arg == "--cap-native") {
            if (++i >= argc)
                throw std::runtime_error("--cap-native requiert on|off");
            if (!parse_bool_value(argv[i], &opts.cap_native))
                throw std::runtime_error("--cap-native attend on|off");
            opts.cap_native_set = true;
        } else if (arg == "--cap-docker") {
            if (++i >= argc)
                throw std::runtime_error("--cap-docker requiert on|off");
            if (!parse_bool_value(argv[i], &opts.cap_docker))
                throw std::runtime_error("--cap-docker attend on|off");
            opts.cap_docker_set = true;
        } else if (arg == "--cap-wsl") {
            if (++i >= argc)
                throw std::runtime_error("--cap-wsl requiert on|off");
            if (!parse_bool_value(argv[i], &opts.cap_wsl))
                throw std::runtime_error("--cap-wsl attend on|off");
            opts.cap_wsl_set = true;
        } else if (arg == "--cap-http") {
            if (++i >= argc)
                throw std::runtime_error("--cap-http requiert on|off");
            if (!parse_bool_value(argv[i], &opts.cap_http))
                throw std::runtime_error("--cap-http attend on|off");
            opts.cap_http_set = true;
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
    if (!opts.mcp_read_only_set) {
        if (const char* env = std::getenv("SILICIUM_MCP_READONLY")) {
            std::string value(env);
            if (value == "1" || value == "true" || value == "yes") {
                opts.mcp_read_only = true;
                opts.mcp_read_only_set = true;
            }
        }
    }
    if (opts.mcp_export_dir.empty()) {
        if (const char* env = std::getenv("SILICIUM_MCP_EXPORT_DIR")) {
            opts.mcp_export_dir = env;
            opts.mcp_read_only = true;
            opts.mcp_read_only_set = true;
        }
    }
    if (!opts.mcp_enable_tools_set) {
        if (const char* env = std::getenv("SILICIUM_MCP_ENABLE_TOOLS")) {
            std::string value(env);
            if (value == "1" || value == "true" || value == "yes") {
                opts.mcp_enable_tools = true;
                opts.mcp_enable_tools_set = true;
                opts.mcp_read_only = true;
                opts.mcp_read_only_set = true;
            }
        }
    }

    return opts;
}

std::string sanitize_task_id(std::string task_id) {
    if (task_id.empty())
        return "task";
    for (char& ch : task_id) {
        const bool valid = (ch >= 'a' && ch <= 'z')
            || (ch >= 'A' && ch <= 'Z')
            || (ch >= '0' && ch <= '9')
            || ch == '-'
            || ch == '_'
            || ch == '.';
        if (!valid)
            ch = '_';
    }
    return task_id;
}

void write_text_file(const std::filesystem::path& path, const std::string& content) {
    std::ofstream out(path, std::ios::out | std::ios::trunc);
    if (!out)
        throw std::runtime_error("Impossible d'ecrire le fichier: " + path.string());
    out << content;
}

void export_mcp_resources(const worker::mcp::McpReadOnlyConnectorAdapter& adapter,
                          const std::filesystem::path& export_dir,
                          const std::string& task_id) {
    std::filesystem::create_directories(export_dir);

    write_text_file(export_dir / "status.current.json",
                    adapter.read_resource(std::string(worker::mcp::kResourceStatusCurrent)));
    write_text_file(export_dir / "reports.recent.json",
                    adapter.read_resource(std::string(worker::mcp::kResourceReportsRecent)));

    if (!task_id.empty()) {
        const std::string safe_task_id = sanitize_task_id(task_id);
        const std::string result_uri = "resources://silicium/results/by-task/" + task_id;
        const std::string logs_uri = "resources://silicium/logs/by-task/" + task_id;
        write_text_file(export_dir / ("result." + safe_task_id + ".json"),
                        adapter.read_resource(result_uri));
        write_text_file(export_dir / ("logs." + safe_task_id + ".json"),
                        adapter.read_resource(logs_uri));
    }
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
        config.capabilities = detect_backend_capabilities(opts);
        if (config.wsl_enabled && !config.capabilities.wsl) {
            config.wsl_enabled = false;
            config.wsl_decision = "capability_unavailable";
        }
        config.mcp.read_only = opts.mcp_read_only;
        config.mcp.enable_control_tools = opts.mcp_enable_tools;
        config.mcp.export_dir = opts.mcp_export_dir;
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
        std::shared_ptr<worker::mcp::McpReadOnlyConnectorAdapter> mcp_adapter;
        if (config.mcp.read_only) {
            worker::mcp::McpReadOnlyAdapterOptions mcp_options{};
            mcp_options.enable_control_tools = config.mcp.enable_control_tools;
            mcp_adapter = std::make_shared<worker::mcp::McpReadOnlyConnectorAdapter>(
                nullptr, nullptr, mcp_options);
            runner.add_observer(mcp_adapter);
        }

        worker::WorkerReport report;
        report.summary_path = runner.summary_path();
        report.mode = opts.mode;

        std::ofstream log_stream;
        if (!opts.log_path.empty())
            log_stream.open(opts.log_path, std::ios::out | std::ios::trunc);

        for (const auto& task : tasks) {
            if (mcp_adapter) {
                if (auto requested_mode = mcp_adapter->consume_mode_request(); requested_mode.has_value()) {
                    runner.set_mode(*requested_mode);
                    report.mode = *requested_mode;
                }
                if (mcp_adapter->consume_interrupt_request()) {
                    worker::TaskReport interrupted;
                    interrupted.partition_id = task.partition_id;
                    interrupted.inputs = task.inputs;
                    interrupted.result.success = false;
                    interrupted.result.error_message = "interrupted_by_mcp";
                    interrupted.telemetry.task_id = task.partition_id;
                    interrupted.telemetry.type = task.type;
                    interrupted.telemetry.status = "interrupted";
                    interrupted.telemetry.linux_policy =
                        worker::fragment_os_action_to_string(config.fragment_os_policy.linux);
                    interrupted.telemetry.windows_policy =
                        worker::fragment_os_action_to_string(config.fragment_os_policy.windows);
                    interrupted.telemetry.wsl_enabled = config.wsl_enabled;
                    interrupted.telemetry.wsl_decision = config.wsl_decision;
                    interrupted.telemetry.required_backend = "none";
                    interrupted.telemetry.routing_decision = "interrupted_by_mcp";
                    interrupted.telemetry.capability_matrix =
                        std::string("native=") + (config.capabilities.native ? "1" : "0")
                        + ",docker=" + (config.capabilities.docker ? "1" : "0")
                        + ",wsl=" + (config.capabilities.wsl ? "1" : "0")
                        + ",http=" + (config.capabilities.http ? "1" : "0");
                    interrupted.telemetry.mcp_enabled = config.mcp.read_only;
                    const auto metrics = mcp_adapter->snapshot_metrics();
                    interrupted.telemetry.mcp_tool_calls = metrics.calls;
                    interrupted.telemetry.mcp_tool_failures = metrics.failures;
                    interrupted.telemetry.mcp_last_tool_latency_ms = metrics.last_latency_ms;
                    interrupted.telemetry.mcp_last_error = metrics.last_error;
                    report.tasks.push_back(std::move(interrupted));
                    mcp_adapter->publish_worker_report(report);
                    if (!config.mcp.export_dir.empty()) {
                        const std::string current_task_id =
                            report.tasks.back().telemetry.task_id.empty()
                                ? report.tasks.back().partition_id
                                : report.tasks.back().telemetry.task_id;
                        export_mcp_resources(*mcp_adapter, config.mcp.export_dir, current_task_id);
                    }
                    break;
                }
            }
            try {
                auto task_report = runner.execute(task);
                if (mcp_adapter) {
                    const auto metrics = mcp_adapter->snapshot_metrics();
                    task_report.telemetry.mcp_enabled = config.mcp.read_only;
                    task_report.telemetry.mcp_tool_calls = metrics.calls;
                    task_report.telemetry.mcp_tool_failures = metrics.failures;
                    task_report.telemetry.mcp_last_tool_latency_ms = metrics.last_latency_ms;
                    task_report.telemetry.mcp_last_error = metrics.last_error;
                }
                if (log_stream) {
                    if (!task_report.result.program_stdout.empty())
                        log_stream << task_report.result.program_stdout;
                    if (!task_report.result.program_stderr.empty())
                        log_stream << task_report.result.program_stderr;
                }
                report.tasks.push_back(std::move(task_report));
                if (mcp_adapter) {
                    mcp_adapter->publish_worker_report(report);
                    if (!config.mcp.export_dir.empty()) {
                        const std::string current_task_id =
                            report.tasks.back().telemetry.task_id.empty()
                                ? report.tasks.back().partition_id
                                : report.tasks.back().telemetry.task_id;
                        export_mcp_resources(*mcp_adapter, config.mcp.export_dir, current_task_id);
                    }
                }
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
                failure.telemetry.required_backend = "none";
                failure.telemetry.routing_decision = "task_exception";
                failure.telemetry.capability_matrix =
                    std::string("native=") + (config.capabilities.native ? "1" : "0")
                    + ",docker=" + (config.capabilities.docker ? "1" : "0")
                    + ",wsl=" + (config.capabilities.wsl ? "1" : "0")
                    + ",http=" + (config.capabilities.http ? "1" : "0");
                if (mcp_adapter) {
                    const auto metrics = mcp_adapter->snapshot_metrics();
                    failure.telemetry.mcp_enabled = config.mcp.read_only;
                    failure.telemetry.mcp_tool_calls = metrics.calls;
                    failure.telemetry.mcp_tool_failures = metrics.failures;
                    failure.telemetry.mcp_last_tool_latency_ms = metrics.last_latency_ms;
                    failure.telemetry.mcp_last_error = metrics.last_error;
                }
                report.tasks.push_back(std::move(failure));
                if (mcp_adapter) {
                    mcp_adapter->publish_worker_report(report);
                    if (!config.mcp.export_dir.empty()) {
                        const std::string current_task_id =
                            report.tasks.back().telemetry.task_id.empty()
                                ? report.tasks.back().partition_id
                                : report.tasks.back().telemetry.task_id;
                        export_mcp_resources(*mcp_adapter, config.mcp.export_dir, current_task_id);
                    }
                }
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
