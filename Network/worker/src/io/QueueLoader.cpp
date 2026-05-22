#include "worker/io/QueueLoader.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>

#include "support/Utils.hpp"

namespace worker {

RegisterValue parse_register_value(const std::string& token) {
    if (token.empty())
        throw std::runtime_error("Valeur vide");

    int base = 10;
    size_t offset = 0;
    if (token.size() > 2 && token[0] == '0' && (token[1] == 'x' || token[1] == 'X')) {
        base = 16;
        offset = 2;
    }

    std::string digits = token.substr(offset);
    if (digits.empty())
        throw std::runtime_error("Valeur numérique invalide: " + token);

    return std::stoull(digits, nullptr, base);
}

std::vector<Task> load_queue_file(const std::string& path) {
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("Impossible d'ouvrir la file de tâches: " + path);

    std::vector<Task> tasks;
    std::string line;
    size_t line_no = 0;

    while (std::getline(file, line)) {
        ++line_no;
        std::string trimmed = fragment::trim(line);
        if (trimmed.empty() || trimmed[0] == '#')
            continue;

        std::istringstream iss(trimmed);
        Task task;
        if (!(iss >> task.partition_id))
            continue;

        std::string token;
        while (iss >> token) {
            size_t eq = token.find('=');

            if (eq == std::string::npos || !eq || eq + 1 >= token.size()) {
                throw std::runtime_error("Ligne " + std::to_string(line_no)
                                         + ": argument invalide \"" + token + "\"");
            }
            std::string reg = token.substr(0, eq);
            std::string value = token.substr(eq + 1);
            try {
                if (reg == "type" || reg == "task_type") {
                    task.type = parse_task_type(value);
                } else {
                    task.inputs[reg] = parse_register_value(value);
                }
            } catch (const std::exception& e) {
                throw std::runtime_error("Ligne " + std::to_string(line_no) + ": " + e.what());
            }
        }

        tasks.push_back(std::move(task));
    }

    return tasks;
}

}  // namespace worker
