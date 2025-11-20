#include "worker/task_serializer.hpp"

#include <cctype>
#include <jansson.h>
#include <sstream>
#include <stdexcept>

#include "fragment/utils.hpp"

#include "worker/queue_loader.hpp"

namespace worker {
namespace {

std::string json_escape(const std::string& value) {
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

std::string format_hex(uint64_t value) {
    std::ostringstream oss;
    oss << "0x" << std::hex << std::nouppercase << value;
    return oss.str();
}

std::vector<uint8_t> decode_hex(const std::string& hex) {
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

std::string encode_hex(const std::vector<uint8_t>& bytes) {
    static constexpr char kHex[] = "0123456789abcdef";
    std::string out;
    out.reserve(bytes.size() * 2);
    for (uint8_t byte : bytes) {
        out.push_back(kHex[(byte >> 4) & 0xF]);
        out.push_back(kHex[byte & 0xF]);
    }
    return out;
}

std::string join_kv_pairs(const std::map<std::string, uint64_t>& values) {
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

std::map<std::string, uint64_t> parse_kv_pairs(const std::vector<std::string>& entries) {
    std::map<std::string, uint64_t> values;
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

std::string join_memory(const std::vector<MemorySnapshot>& pages) {
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

std::vector<MemorySnapshot> parse_memory(const std::vector<std::string>& entries) {
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

std::string build_kv_array(const std::map<std::string, uint64_t>& values,
                           const std::string& name) {
    std::ostringstream oss;
    oss << "  \"" << name << "\":[" << join_kv_pairs(values) << "]";
    return oss.str();
}

json_t* load_json_root(const std::string& content) {
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

std::string get_json_string(json_t* root, const char* key) {
    if (json_t* v = json_object_get(root, key); json_is_string(v))
        return json_string_value(v);
    return {};
}

bool get_json_bool(json_t* root, const char* key, bool default_value = false) {
    if (json_t* v = json_object_get(root, key); json_is_boolean(v))
        return json_is_true(v);
    return default_value;
}

uint64_t get_json_uint64(json_t* root, const char* key, uint64_t default_value = 0) {
    if (json_t* v = json_object_get(root, key); json_is_integer(v))
        return static_cast<uint64_t>(json_integer_value(v));
    return default_value;
}

std::vector<std::string> get_json_string_array(json_t* root, const char* key) {
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

std::map<std::string, uint64_t> parse_register_map(json_t* root, const char* key) {
    return parse_kv_pairs(get_json_string_array(root, key));
}

std::vector<MemorySnapshot> parse_memory_array(json_t* root, const char* key) {
    return parse_memory(get_json_string_array(root, key));
}

}  // namespace

std::string serialize_task_payload(const TaskPayload& payload) {
    std::ostringstream oss;
    oss << "{\n"
        << "  \"partition_id\":\"" << json_escape(payload.partition_id) << "\",\n"
        << "  \"asm_path\":\"" << json_escape(payload.asm_path) << "\",\n"
        << "  \"binary_path\":\"" << json_escape(payload.binary_path) << "\",\n"
        << "  \"native\":" << (payload.native_mode ? "true" : "false") << ",\n"
        << build_kv_array(payload.inputs, "inputs") << ",\n"
        << build_kv_array(payload.register_state, "register_state") << ",\n"
        << "  \"memory\":[" << join_memory(payload.memory_state) << "]\n"
        << "}\n";
    return oss.str();
}

TaskPayload deserialize_task_payload(const std::string& content) {
    json_t* root = load_json_root(content);
    TaskPayload payload;
    payload.partition_id = get_json_string(root, "partition_id");
    payload.asm_path = get_json_string(root, "asm_path");
    payload.binary_path = get_json_string(root, "binary_path");
    payload.native_mode = get_json_bool(root, "native", false);
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
        << "  \"success\":" << (result.success ? "true" : "false") << ",\n"
        << "  \"error\":\"" << json_escape(result.error_message) << "\",\n"
        << "  \"stdout\":\"" << json_escape(result.program_stdout) << "\",\n"
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
    fragment::ExecutionResult result;
    result.success = get_json_bool(root, "success", false);
    result.error_message = get_json_string(root, "error");
    result.program_stdout = get_json_string(root, "stdout");
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
