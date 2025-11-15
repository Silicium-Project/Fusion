#include "worker/task_serializer.hpp"

#include <cctype>
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

std::map<std::string, uint64_t> parse_register_map(const std::string& content,
                                                    const std::string& key) {
    auto array = fragment::extract_json_array(content, key);
    return parse_kv_pairs(array);
}

std::vector<MemorySnapshot> parse_memory_array(const std::string& content,
                                               const std::string& key) {
    auto array = fragment::extract_json_array(content, key);
    return parse_memory(array);
}

uint64_t extract_json_uint64(const std::string& content,
                             const std::string& key,
                             uint64_t default_value = 0) {
    const std::string pattern = '\"' + key + '\"';
    size_t pos = content.find(pattern);
    if (pos == std::string::npos)
        return default_value;
    pos = content.find(':', pos);
    if (pos == std::string::npos)
        return default_value;
    ++pos;
    while (pos < content.size() && std::isspace(static_cast<unsigned char>(content[pos])))
        ++pos;
    size_t end = pos;
    while (end < content.size() && std::isdigit(static_cast<unsigned char>(content[end])))
        ++end;
    if (end == pos)
        return default_value;
    return std::stoull(content.substr(pos, end - pos));
}

std::string build_kv_array(const std::map<std::string, uint64_t>& values,
                           const std::string& name) {
    std::ostringstream oss;
    oss << "  \"" << name << "\":[" << join_kv_pairs(values) << "]";
    return oss.str();
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
    TaskPayload payload;
    payload.partition_id = fragment::extract_json_string(content, "partition_id");
    payload.asm_path = fragment::extract_json_string(content, "asm_path");
    payload.binary_path = fragment::extract_json_string(content, "binary_path");
    payload.native_mode = fragment::extract_json_bool(content, "native", false);
    payload.inputs = parse_register_map(content, "inputs");
    payload.register_state = parse_register_map(content, "register_state");
    payload.memory_state = parse_memory_array(content, "memory");
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
    fragment::ExecutionResult result;
    result.success = fragment::extract_json_bool(content, "success", false);
    result.error_message = fragment::extract_json_string(content, "error");
    result.program_stdout = fragment::extract_json_string(content, "stdout");
    result.initial_regs = parse_register_map(content, "initial_regs");
    result.final_regs = parse_register_map(content, "final_regs");
    result.memory_patches = parse_patches(fragment::extract_json_array(content, "memory_patches"));
    result.instructions_executed = extract_json_uint64(content, "instructions", 0);
    result.memory_accesses = extract_json_uint64(content, "memory_accesses", 0);
    // changed_regs is derived from initial/final at reporting time if needed.
    if (!result.initial_regs.empty() && !result.final_regs.empty()) {
        for (const auto& [reg, final_value] : result.final_regs) {
            auto it = result.initial_regs.find(reg);
            uint64_t initial_value = (it != result.initial_regs.end()) ? it->second : 0;
            if (initial_value != final_value)
                result.changed_regs[reg] = {initial_value, final_value};
        }
    }
    return result;
}

}  // namespace worker
