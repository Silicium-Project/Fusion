#pragma once

#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>

namespace worker {

using PartitionId = std::string;
using RegisterValue = std::uint64_t;
using RegisterState = std::map<std::string, RegisterValue>;

enum class TaskType {
    Binary,
    Health
};

inline std::string task_type_to_string(TaskType type) {
    switch (type) {
        case TaskType::Binary:
            return "binary";
        case TaskType::Health:
            return "health";
        default:
            return "binary";
    }
}

inline TaskType parse_task_type(const std::string& value) {
    if (value == "binary")
        return TaskType::Binary;
    if (value == "health" || value == "check")
        return TaskType::Health;
    throw std::runtime_error("Type de tâche inconnu: " + value);
}

}  // namespace worker
