#include "fragment/partition_summary.hpp"

#include <jansson.h>

#include <queue>
#include <unordered_map>

#include "fragment/utils.hpp"

namespace fragment {

namespace {

std::string to_string_safe(json_t* value) {
    if (json_is_string(value))
        return json_string_value(value);
    return {};
}

std::optional<uint64_t> parse_hex_address(json_t* value) {
    if (json_is_integer(value))
        return static_cast<uint64_t>(json_integer_value(value));
    if (json_is_string(value)) {
        std::string str = json_string_value(value);
        if (str.rfind("0x", 0) == 0 || str.rfind("0X", 0) == 0)
            str = str.substr(2);
        if (str.empty())
            return std::nullopt;
        try {
            return std::stoull(str, nullptr, 16);
        } catch (...) {
            return std::nullopt;
        }
    }
    return std::nullopt;
}

std::vector<std::string> string_array(json_t* value) {
    std::vector<std::string> out;
    if (!json_is_array(value))
        return out;
    size_t idx = 0;
    json_t* item = nullptr;
    json_array_foreach(value, idx, item) {
        if (json_is_string(item))
            out.emplace_back(json_string_value(item));
    }
    return out;
}

MemoryRegion parse_memory_region(json_t* obj) {
    MemoryRegion region;
    if (!json_is_object(obj))
        return region;
    region.name = to_string_safe(json_object_get(obj, "name"));
    if (auto addr = parse_hex_address(json_object_get(obj, "address")))
        region.address = *addr;
    if (auto bytes_str = json_object_get(obj, "bytes"); json_is_string(bytes_str)) {
        const std::string hex = json_string_value(bytes_str);
        if (hex.size() % 2 == 0) {
            region.bytes.reserve(hex.size() / 2);
            for (size_t i = 0; i + 1 < hex.size(); i += 2) {
                auto byte = static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16));
                region.bytes.push_back(byte);
            }
        }
    }
    return region;
}

PartitionInfo parse_partition(json_t* obj) {
    if (!json_is_object(obj))
        throw std::runtime_error("Partition invalide dans le summary");

    PartitionInfo info;
    info.id = to_string_safe(json_object_get(obj, "id"));
    info.asm_path = to_string_safe(json_object_get(obj, "asm"));
    info.bin_path = to_string_safe(json_object_get(obj, "bin"));
    info.wrapper_path = to_string_safe(json_object_get(obj, "wrapper"));
    info.start_address = parse_hex_address(json_object_get(obj, "start"));
    info.end_address = parse_hex_address(json_object_get(obj, "end"));
    if (json_t* size = json_object_get(obj, "size"); json_is_integer(size))
        info.binary_size = static_cast<size_t>(json_integer_value(size));
    if (json_t* par = json_object_get(obj, "parallelizable"); json_is_true(par))
        info.parallelizable = true;
    if (json_t* disp = json_object_get(obj, "requires_display"); json_is_true(disp))
        info.requires_display = true;

    for (auto& v : string_array(json_object_get(obj, "parents")))
        info.parents.push_back(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "dependencies")))
        info.dependencies.push_back(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "unresolved_calls")))
        info.unresolved_calls.push_back(std::move(v));

    for (auto& v : string_array(json_object_get(obj, "inputs")))
        info.inputs.insert(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "external_inputs")))
        info.external_inputs.insert(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "external_calls")))
        info.external_calls.insert(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "outputs")))
        info.outputs.insert(std::move(v));
    for (auto& v : string_array(json_object_get(obj, "required_libraries")))
        info.required_libraries.insert(std::move(v));

    if (info.id.empty() || info.asm_path.empty())
        throw std::runtime_error("Résumé invalide: partition sans identifiant ou fichier ASM");
    return info;
}

void resolve_dependencies(std::vector<PartitionInfo>& partitions) {
    std::unordered_map<std::string, PartitionInfo*> lookup;
    lookup.reserve(partitions.size());
    for (auto& p : partitions)
        lookup.emplace(p.id, &p);

    for (auto& partition : partitions) {
        partition.resolved_dependencies.clear();
        for (const auto& dep_id : partition.dependencies) {
            auto it = lookup.find(dep_id);
            if (it == lookup.end())
                continue;
            const PartitionInfo* dep = it->second;
            PartitionDependency dep_info;
            dep_info.id = dep->id;
            dep_info.asm_path = dep->asm_path;
            dep_info.bin_path = dep->bin_path;
            dep_info.start_address = dep->start_address;
            dep_info.binary_size = dep->binary_size;
            partition.resolved_dependencies.push_back(std::move(dep_info));
        }
    }
}

PartitionSummary parse_summary(json_t* root) {
    if (!json_is_object(root))
        throw std::runtime_error("Résumé invalide (racine)");

    PartitionSummary summary;
    summary.binary_path = to_string_safe(json_object_get(root, "binary"));

    for (auto& v : string_array(json_object_get(root, "required_libraries")))
        summary.required_libraries.push_back(std::move(v));

    if (json_t* libs = json_object_get(root, "libraries"); json_is_array(libs)) {
        size_t idx = 0;
        json_t* item = nullptr;
        json_array_foreach(libs, idx, item) {
            if (!json_is_object(item))
                continue;
            LibraryInfo lib;
            lib.name = to_string_safe(json_object_get(item, "name"));
            lib.path = to_string_safe(json_object_get(item, "path"));
            lib.soname = to_string_safe(json_object_get(item, "soname"));
            lib.build_id = to_string_safe(json_object_get(item, "build_id"));
            if (!lib.name.empty())
                summary.libraries.push_back(std::move(lib));
        }
    }

    json_t* parts = json_object_get(root, "partitions");
    if (!json_is_array(parts))
        throw std::runtime_error("Résumé invalide: champ \"partitions\" manquant");
    size_t idx = 0;
    json_t* item = nullptr;
    json_array_foreach(parts, idx, item) {
        summary.partitions.push_back(parse_partition(item));
    }
    if (summary.partitions.empty())
        throw std::runtime_error("Résumé valide mais aucune partition trouvée");

    if (json_t* mem = json_object_get(root, "initial_memory"); json_is_array(mem)) {
        size_t midx = 0;
        json_t* memb = nullptr;
        json_array_foreach(mem, midx, memb)
            summary.initial_memory.push_back(parse_memory_region(memb));
    }

    resolve_dependencies(summary.partitions);
    return summary;
}

using Graph = std::unordered_map<std::string, std::vector<std::string>>;

std::vector<std::string> order_partitions_impl(const std::vector<PartitionInfo>& partitions) {
    Graph adjacency;
    std::unordered_map<std::string, size_t> indegree;
    for (const auto& partition : partitions) {
        indegree[partition.id] = partition.parents.size();
        adjacency[partition.id];
    }
    for (const auto& partition : partitions)
        for (const auto& dep : partition.dependencies)
            adjacency[partition.id].push_back(dep);

    std::priority_queue<std::string, std::vector<std::string>, std::greater<std::string>> ready;
    for (const auto& [id, degree] : indegree)
        if (degree == 0)
            ready.push(id);

    std::vector<std::string> order;
    order.reserve(partitions.size());
    while (!ready.empty()) {
        auto id = ready.top();
        ready.pop();
        order.push_back(id);
        for (const auto& dep : adjacency[id]) {
            if (--indegree[dep] == 0)
                ready.push(dep);
        }
    }
    if (order.size() != partitions.size())
        throw std::runtime_error("Cycle détecté dans les partitions");
    return order;
}

}  // namespace

PartitionSummary load_partition_summary(const std::string& summary_path) {
    json_error_t error;
    json_t* root = json_load_file(summary_path.c_str(), 0, &error);
    if (!root)
        throw std::runtime_error("Impossible de parser le summary: " + std::string(error.text));
    PartitionSummary summary;
    try {
        summary = parse_summary(root);
    } catch (...) {
        json_decref(root);
        throw;
    }
    json_decref(root);
    return summary;
}

std::vector<std::string> order_partitions(const PartitionSummary& summary) {
    return order_partitions_impl(summary.partitions);
}

std::vector<std::string> order_partitions(const std::vector<PartitionInfo>& partitions) {
    return order_partitions_impl(partitions);
}

}  // namespace fragment
