#include "worker/task/TaskSerializer.hpp"

#include <cctype>
#include <jansson.h>
#include <sstream>
#include <stdexcept>
#include <map>

#include "worker/core/WorkerConfig.hpp"
#include "support/Utils.hpp"

#include "worker/io/QueueLoader.hpp"

namespace worker {

static std::string json_escape(const std::string& value) {
    std::ostringstream oss;
    for (char c : value) {
        switch (c) {
            case '"': oss << "\\\""; break;
            case '\\': oss << "\\\\"; break;
            case '\n': oss << "\\n"; break;
            case '\r': oss << "\\r"; break;
            case '\t': oss << "\\t"; break;
            default:
                oss << c;
        }
    }
    return oss.str();
}

static std::string format_hex(uint64_t value) {
    std::ostringstream oss;
    oss << "0x" << std::hex << std::nouppercase << value;
    return oss.str();
}

static std::vector<uint8_t> decode_hex(const std::string& hex) {
    if (hex.size() % 2 != 0)
        throw std::runtime_error("Hex string length must be even");

    std::vector<uint8_t> bytes;
    bytes.reserve(hex.size() / 2);
    for (size_t i = 0; i < hex.size(); i += 2) {
        auto byte = static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16));
        bytes.push_back(byte);
    }
    return bytes;
}

static std::string encode_hex(const std::vector<uint8_t>& bytes) {
    static constexpr char kHex[] = "0123456789abcdef";
    std::string out;
    out.reserve(bytes.size() * 2);
    for (uint8_t byte : bytes) {
        out.push_back(kHex[(byte >> 4) & 0xF]);
        out.push_back(kHex[byte & 0xF]);
    }
    return out;
}

static std::string join_kv_pairs(const RegisterState& values) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& [reg, value] : values) {
        if (!first)
            oss << ',';
        first = false;
        oss << '\"' << json_escape(reg) << '=' << json_escape(format_hex(value)) << '\"';
    }
    return oss.str();
}

static RegisterState parse_kv_pairs(const std::vector<std::string>& entries) {
    RegisterState values;
    for (const auto& entry : entries) {
        const auto pos = entry.find('=');
        if (pos == std::string::npos)
            throw std::runtime_error("Entrée invalide: " + entry);
        const std::string reg = entry.substr(0, pos);
        const std::string val = entry.substr(pos + 1);
        values[reg] = parse_register_value(val);
    }
    return values;
}

static std::string join_memory(const std::vector<MemorySnapshot>& pages) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& page : pages) {
        if (!first)
            oss << ',';
        first = false;
        oss << '\"' << json_escape(format_hex(page.address)) << ':'
            << json_escape(encode_hex(page.bytes)) << '\"';
    }
    return oss.str();
}

static std::vector<MemorySnapshot> parse_memory(const std::vector<std::string>& entries) {
    std::vector<MemorySnapshot> pages;
    pages.reserve(entries.size());
    for (const auto& entry : entries) {
        auto pos = entry.find(':');
        if (pos == std::string::npos)
            throw std::runtime_error("Page mémoire invalide: " + entry);
        MemorySnapshot snapshot;
        snapshot.address = parse_register_value(entry.substr(0, pos));
        snapshot.bytes = decode_hex(entry.substr(pos + 1));
        pages.push_back(std::move(snapshot));
    }
    return pages;
}

static std::string join_fd_outputs(const fragment::FdTable& fds) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& [fd, cap] : fds) {
        if (!first)
            oss << ',';
        first = false;
        oss << '\"' << fd << "\":{"
            << "\"data\":\"" << json_escape(encode_hex(std::vector<uint8_t>(cap.data.begin(), cap.data.end()))) << "\"";
        if (!cap.alias.empty())
            oss << ",\"alias\":\"" << json_escape(cap.alias) << "\"";
        oss << "}";
    }
    return oss.str();
}

static fragment::FdTable parse_fd_outputs(json_t* root) {
    fragment::FdTable out;
    if (json_t* obj = json_object_get(root, "fd_outputs"); json_is_object(obj)) {
        const char* key;
        json_t* val;
        json_object_foreach(obj, key, val) {
            if (!json_is_object(val))
                continue;
            try {
                int fd = std::stoi(key);
                fragment::FdCapture cap;
                if (json_t* data = json_object_get(val, "data"); json_is_string(data)) {
                    auto bytes = decode_hex(json_string_value(data));
                    cap.data.assign(bytes.begin(), bytes.end());
                }
                if (json_t* alias = json_object_get(val, "alias"); json_is_string(alias))
                    cap.alias = json_string_value(alias);
                out.set(fd, std::move(cap));
            } catch (...) {
                continue;
            }
        }
    }
    return out;
}

static std::string join_fd_redirections(const std::vector<fragment::FdRule>& fds) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& fd : fds) {
        if (!first)
            oss << ',';
        first = false;
        oss << "{"
            << "\"fd\":" << fd.fd << ","
            << "\"capture\":" << (fd.capture ? "true" : "false") << ",";
        oss << "\"input\":\"" << json_escape(encode_hex(std::vector<uint8_t>(fd.input_data.begin(), fd.input_data.end()))) << "\",";
        oss << "\"alias\":\"" << json_escape(fd.alias) << "\"";
        oss << "}";
    }
    return oss.str();
}

static std::vector<fragment::FdRule> parse_fd_redirections(json_t* root) {
    std::vector<fragment::FdRule> out;
    if (json_t* arr = json_object_get(root, "fd_redirections"); json_is_array(arr)) {
        size_t idx = 0;
        json_t* item = nullptr;
        json_array_foreach(arr, idx, item) {
            if (!json_is_object(item))
                continue;
            fragment::FdRule fd{};
            if (json_t* v = json_object_get(item, "fd"); json_is_integer(v))
                fd.fd = static_cast<int>(json_integer_value(v));
            if (json_t* v = json_object_get(item, "capture"); json_is_boolean(v))
                fd.capture = json_is_true(v);
            if (json_t* v = json_object_get(item, "input"); json_is_string(v)) {
                auto bytes = decode_hex(json_string_value(v));
                fd.input_data.assign(bytes.begin(), bytes.end());
            }
            if (json_t* v = json_object_get(item, "alias"); json_is_string(v))
                fd.alias = json_string_value(v);
            out.push_back(std::move(fd));
        }
    }
    return out;
}

static std::string build_kv_array(const RegisterState& values, const std::string& name) {
    std::ostringstream oss;
    oss << "  \"" << name << "\":[" << join_kv_pairs(values) << "]";
    return oss.str();
}

static json_t* load_json_root(const std::string& content) {
    json_error_t err;
    json_t* root = json_loads(content.c_str(), 0, &err);
    if (!root)
        throw std::runtime_error(std::string("JSON invalide: ") + err.text);
    if (!json_is_object(root)) {
        json_decref(root);
        throw std::runtime_error("JSON inattendu (objet attendu)");
    }
    return root;
}

static std::string get_json_string(json_t* root, const char* key) {
    if (json_t* v = json_object_get(root, key); json_is_string(v))
        return json_string_value(v);
    return {};
}

static bool get_json_bool(json_t* root, const char* key, bool default_value = false) {
    if (json_t* v = json_object_get(root, key); json_is_boolean(v))
        return json_is_true(v);
    return default_value;
}

static uint64_t get_json_uint64(json_t* root, const char* key, uint64_t default_value = 0) {
    if (json_t* v = json_object_get(root, key); json_is_integer(v))
        return static_cast<uint64_t>(json_integer_value(v));
    return default_value;
}

static uint32_t parse_schema_version(json_t* root,
                                     const char* key,
                                     uint32_t current_version,
                                     const char* schema_name) {
    json_t* value = json_object_get(root, key);
    if (!value)
        return current_version;
    if (!json_is_integer(value))
        throw std::runtime_error(std::string(schema_name) + " schema_version invalide");
    const auto parsed = static_cast<long long>(json_integer_value(value));
    if (parsed <= 0)
        throw std::runtime_error(std::string(schema_name) + " schema_version invalide");
    if (static_cast<uint32_t>(parsed) > current_version)
        throw std::runtime_error(std::string(schema_name) + " schema_version non supporte");
    return static_cast<uint32_t>(parsed);
}

static std::vector<std::string> get_json_string_array(json_t* root, const char* key) {
    std::vector<std::string> out;
    if (json_t* arr = json_object_get(root, key); json_is_array(arr)) {
        size_t idx = 0;
        json_t* item = nullptr;
        json_array_foreach(arr, idx, item) {
            if (json_is_string(item))
                out.emplace_back(json_string_value(item));
        }
    }
    return out;
}

static RegisterState parse_register_map(json_t* root, const char* key) {
    return parse_kv_pairs(get_json_string_array(root, key));
}

static std::vector<MemorySnapshot> parse_memory_array(json_t* root, const char* key) {
    return parse_memory(get_json_string_array(root, key));
}

static std::string mode_to_string(ExecutionMode mode) {
    switch (mode) {
        case ExecutionMode::Native: return "native";
        case ExecutionMode::Dynamo: return "dynamo";
        case ExecutionMode::Auto: return "auto";
        case ExecutionMode::Emulator:
        default: return "emu";
    }
}

static ExecutionMode parse_mode(const std::string& value) {
    if (value == "native")
        return ExecutionMode::Native;
    if (value == "dynamo")
        return ExecutionMode::Dynamo;
    if (value == "auto")
        return ExecutionMode::Auto;
    return ExecutionMode::Emulator;
}

std::string serialize_task_payload(const TaskPayload& payload) {
    std::ostringstream oss;
    oss << "{\n"
        << "  \"schema_version\":" << payload.schema_version << ",\n"
        << "  \"type\":\"" << json_escape(task_type_to_string(payload.type)) << "\",\n"
        << "  \"partition_id\":\"" << json_escape(payload.partition_id) << "\",\n"
        << "  \"asm_path\":\"" << json_escape(payload.asm_path) << "\",\n"
        << "  \"binary_path\":\"" << json_escape(payload.binary_path) << "\",\n"
        << "  \"mode\":\"" << mode_to_string(payload.mode) << "\",\n"
        << "  \"fd_redirections\":[" << join_fd_redirections(payload.fd_rules) << "],\n"
        << build_kv_array(payload.inputs, "inputs") << ",\n"
        << build_kv_array(payload.register_state, "register_state") << ",\n"
        << "  \"memory\":[" << join_memory(payload.memory_state) << "]\n"
        << "}\n";
    return oss.str();
}

TaskPayload deserialize_task_payload(const std::string& content) {
    json_t* root = load_json_root(content);
    TaskPayload payload;
    payload.schema_version = parse_schema_version(
        root, "schema_version", kTaskPayloadSchemaVersion, "TaskPayload");
    const std::string type = get_json_string(root, "type");
    if (type.empty())
        payload.type = TaskType::Binary;
    else
        payload.type = parse_task_type(type);
    payload.partition_id = get_json_string(root, "partition_id");
    payload.asm_path = get_json_string(root, "asm_path");
    payload.binary_path = get_json_string(root, "binary_path");
    payload.mode = parse_mode(get_json_string(root, "mode"));
    payload.fd_rules = parse_fd_redirections(root);
    payload.inputs = parse_register_map(root, "inputs");
    payload.register_state = parse_register_map(root, "register_state");
    payload.memory_state = parse_memory_array(root, "memory");
    json_decref(root);
    return payload;
}

static std::string join_patches(const std::vector<fragment::MemoryPatch>& patches) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& patch : patches) {
        if (!first)
            oss << ',';
        first = false;
        oss << '\"' << json_escape(format_hex(patch.address)) << ':'
            << json_escape(encode_hex(patch.after)) << '\"';
    }
    return oss.str();
}

std::string serialize_execution_result(const fragment::ExecutionResult& result) {
    std::ostringstream oss;
    oss << "{\n"
        << "  \"schema_version\":" << kExecutionResultSchemaVersion << ",\n"
        << "  \"success\":" << (result.success ? "true" : "false") << ",\n"
        << "  \"error\":\"" << json_escape(result.error_message) << "\",\n"
        << "  \"stdout\":\"" << json_escape(result.program_stdout) << "\",\n"
        << "  \"stderr\":\"" << json_escape(result.program_stderr) << "\",\n"
        << "  \"fd_outputs\":{" << join_fd_outputs(result.fd_outputs) << "},\n"
        << build_kv_array(result.initial_regs, "initial_regs") << ",\n"
        << build_kv_array(result.final_regs, "final_regs") << ",\n"
        << "  \"memory_patches\":[" << join_patches(result.memory_patches) << "],\n"
        << "  \"instructions\":" << result.instructions_executed << ",\n"
        << "  \"memory_accesses\":" << result.memory_accesses << "\n"
        << "}\n";
    return oss.str();
}

static std::vector<fragment::MemoryPatch> parse_patches(const std::vector<std::string>& entries) {
    std::vector<fragment::MemoryPatch> patches;
    patches.reserve(entries.size());
    for (const auto& entry : entries) {
        auto pos = entry.find(':');
        if (pos == std::string::npos)
            throw std::runtime_error("Patch mémoire invalide: " + entry);
        fragment::MemoryPatch patch;
        patch.address = parse_register_value(entry.substr(0, pos));
        patch.after = decode_hex(entry.substr(pos + 1));
        patches.push_back(std::move(patch));
    }
    return patches;
}

fragment::ExecutionResult deserialize_execution_result(const std::string& content) {
    json_t* root = load_json_root(content);
    parse_schema_version(root,
                         "schema_version",
                         kExecutionResultSchemaVersion,
                         "ExecutionResult");
    fragment::ExecutionResult result;
    result.success = get_json_bool(root, "success", false);
    result.error_message = get_json_string(root, "error");
    result.program_stdout = get_json_string(root, "stdout");
    result.program_stderr = get_json_string(root, "stderr");
    result.fd_outputs = parse_fd_outputs(root);
    result.initial_regs = parse_register_map(root, "initial_regs");
    result.final_regs = parse_register_map(root, "final_regs");
    result.memory_patches = parse_patches(get_json_string_array(root, "memory_patches"));
    result.instructions_executed = get_json_uint64(root, "instructions", 0);
    result.memory_accesses = get_json_uint64(root, "memory_accesses", 0);
    // changed_regs is derived from initial/final at reporting time if needed.
    if (!result.initial_regs.empty() && !result.final_regs.empty()) {
        for (const auto& [reg, final_value] : result.final_regs) {
            auto it = result.initial_regs.find(reg);
            uint64_t initial_value = (it != result.initial_regs.end()) ? it->second : 0;
            if (initial_value != final_value)
                result.changed_regs[reg] = {initial_value, final_value};
        }
    }
    json_decref(root);
    return result;
}

}  // namespace worker
