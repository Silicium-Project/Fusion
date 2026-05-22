#include <fstream>
#include <iostream>
#include <stdexcept>

#include "cli/Cli.hpp"
#include "worker/task/TaskSerializer.hpp"
#include "worker/task/TaskTypes.hpp"

namespace {

struct RunnerOptions {
    std::string input_path;
    std::string output_path;
};

RunnerOptions parse_options(int argc, char** argv) {
    RunnerOptions opts;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--input") {
            if (++i >= argc)
                throw std::runtime_error("--input requiert un fichier");
            opts.input_path = argv[i];
        } else if (arg == "--output") {
            if (++i >= argc)
                throw std::runtime_error("--output requiert un fichier");
            opts.output_path = argv[i];
        } else if (arg == "--help") {
            std::cout << "Usage: dynamo_fragment_runner --input in.json --output out.json\n";
            std::exit(0);
        } else
            throw std::runtime_error("Option inconnue: " + arg);
    }
    if (opts.input_path.empty() || opts.output_path.empty())
        throw std::runtime_error("--input et --output sont obligatoires");
    return opts;
}

std::string read_file(const std::string& path) {
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("Impossible d'ouvrir " + path);
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

void write_file(const std::string& path, const std::string& content) {
    std::ofstream file(path, std::ios::out | std::ios::trunc);
    if (!file)
        throw std::runtime_error("Impossible d'écrire " + path);
    file << content;
}

void apply_memory(fragment::FragmentExecutor& executor,
                  const std::vector<worker::MemorySnapshot>& pages) {
    for (const auto& page : pages)
        executor.apply_memory_bytes(page.address, page.bytes);
}

void apply_registers(fragment::FragmentExecutor& executor,
                     const worker::RegisterState& register_state,
                     const worker::RegisterState& overrides) {
    for (const auto& [reg, value] : register_state) {
        if (overrides.count(reg))
            continue;
        executor.set_input(reg, value);
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const RunnerOptions opts = parse_options(argc, argv);
        const std::string payload_text = read_file(opts.input_path);
        worker::TaskPayload payload = worker::deserialize_task_payload(payload_text);

        fragment::ExecutorConfig config;
        const bool use_native = payload.mode == worker::ExecutionMode::Native
                             || payload.mode == worker::ExecutionMode::Auto
                             || payload.mode == worker::ExecutionMode::Dynamo;
        config.use_native_execution = use_native;
        config.binary_path = payload.binary_path;
        config.fd_rules = payload.fd_rules;
        fragment::FragmentExecutor executor(config);

        apply_memory(executor, payload.memory_state);
        apply_registers(executor, payload.register_state, payload.inputs);
        executor.set_inputs(payload.inputs);

        fragment::ExecutionEntry entry;
        entry.name = payload.partition_id;
        entry.asm_path = payload.asm_path;

        fragment::ExecutionResult result;
        const bool executed = fragment::execute_entry(entry,
                                                      use_native,
                                                      false,
                                                      executor,
                                                      result);
        if (!executed) {
            result.success = false;
            if (result.error_message.empty())
                result.error_message = "Impossible d'exécuter le fragment";
        }

        write_file(opts.output_path, worker::serialize_execution_result(result));
        return result.success ? 0 : 1;
    } catch (const std::exception& e) {
        std::cerr << "dynamo_fragment_runner: " << e.what() << "\n";
        return 1;
    }
}
