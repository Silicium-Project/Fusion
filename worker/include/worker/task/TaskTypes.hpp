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
    Binary
};

inline std::string task_type_to_string(TaskType type) {
    switch (type) {
        case TaskType::Binary:
        default:
            return "binary";
    }
}

inline TaskType parse_task_type(const std::string& value) {
    if (value == "binary")
        return TaskType::Binary;
    throw std::runtime_error("Type de tâche inconnu: " + value);
}

}  // namespace worker
