#include "fragment/partition_summary.hpp"

#include <jansson.h>

#include <queue>
#include <unordered_map>
#include <fstream>
#include <functional>
#include <cstdint>
#include <sstream>
#include <algorithm>
#include <iomanip>
#include <filesystem>

#include "fragment/utils.hpp"
#include "fragment/hash.hpp"
#include "fragment/json_hasher.hpp"

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

    std::string hash_bytes(const std::vector<uint8_t>& data) {
        FnvHasher h;
        for (auto b : data)
            h.add_byte(b);
        return h.hex();
    }

    std::string hash_file(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file.is_open())
            return {};
        std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                    std::istreambuf_iterator<char>());
        return hash_bytes(buffer);
    }

    std::string compute_partition_hash(const PartitionInfo& p) {
        json_t* obj = json_object();
        json_object_set_new(obj, "id", json_string(p.id.c_str()));
        json_object_set_new(obj, "start", json_integer(static_cast<long long>(p.start_address.value_or(0))));
        json_object_set_new(obj, "end", json_integer(static_cast<long long>(p.end_address.value_or(0))));
        json_object_set_new(obj, "bin_hash", json_string(p.bin_hash.c_str()));
        json_object_set_new(obj, "size", json_integer(static_cast<long long>(p.binary_size)));
        json_object_set_new(obj, "parallelizable", p.parallelizable ? json_true() : json_false());
        json_object_set_new(obj, "requires_display", p.requires_display ? json_true() : json_false());

        auto set_to_array = [](const auto& container) {
            json_t* arr = json_array();
            std::vector<std::string> sorted(container.begin(), container.end());
            std::sort(sorted.begin(), sorted.end());
            for (const auto& s : sorted)
                json_array_append_new(arr, json_string(s.c_str()));
            return arr;
        };
        auto vec_to_array = [](const auto& vec, bool sort_vec = true) {
            std::vector<std::string> items(vec.begin(), vec.end());
            if (sort_vec)
                std::sort(items.begin(), items.end());
            json_t* arr = json_array();
            for (const auto& s : items)
                json_array_append_new(arr, json_string(s.c_str()));
            return arr;
        };

        json_object_set_new(obj, "inputs", set_to_array(p.inputs));
        json_object_set_new(obj, "external_inputs", set_to_array(p.external_inputs));
        json_object_set_new(obj, "outputs", set_to_array(p.outputs));
        json_object_set_new(obj, "external_calls", set_to_array(p.external_calls));
        json_object_set_new(obj, "required_libraries", set_to_array(p.required_libraries));
        json_object_set_new(obj, "parents", vec_to_array(p.parents));
        json_object_set_new(obj, "dependencies", vec_to_array(p.dependencies));
        json_object_set_new(obj, "unresolved_calls", vec_to_array(p.unresolved_calls));

        JsonHasher hasher(std::make_unique<DomainHasher<>>("partition"));
        hasher.add(obj);
        json_decref(obj);
        return hasher.hex();
    }

    std::string compute_memory_hash(const std::vector<MemoryRegion>& segments) {
        json_t* arr = json_array();
        for (const auto& seg : segments) {
            json_t* obj = json_object();
            json_object_set_new(obj, "name", json_string(seg.name.c_str()));
            json_object_set_new(obj, "address", json_integer(static_cast<long long>(seg.address)));
            std::ostringstream oss;
            oss << std::hex << std::setfill('0');
            for (auto b : seg.bytes)
                oss << std::setw(2) << static_cast<int>(b);
            json_object_set_new(obj, "bytes", json_string(oss.str().c_str()));
            json_array_append_new(arr, obj);
        }
        JsonHasher hasher(std::make_unique<DomainHasher<>>("memory"));
        hasher.add(arr);
        json_decref(arr);
        return hasher.hex();
    }

    std::string compute_summary_hash(const PartitionSummary& summary) {
        json_t* root = json_object();
        json_object_set_new(root, "binary_hash", json_string(summary.binary_hash.c_str()));
        json_object_set_new(root, "memory_hash", json_string(summary.memory_hash.c_str()));
        json_object_set_new(root, "can_split", summary.can_split ? json_true() : json_false());

        auto required = summary.required_libraries;
        std::sort(required.begin(), required.end());
        json_t* req_arr = json_array();
        for (const auto& r : required)
            json_array_append_new(req_arr, json_string(r.c_str()));
        json_object_set_new(root, "required_libraries", req_arr);

        auto libs = summary.libraries;
        std::sort(libs.begin(), libs.end(), [](const auto& a, const auto& b) { return a.name < b.name; });
        json_t* libs_arr = json_array();
        for (const auto& lib : libs) {
            json_t* obj = json_object();
            json_object_set_new(obj, "name", json_string(lib.name.c_str()));
            json_object_set_new(obj, "path", json_string(lib.path.c_str()));
            json_object_set_new(obj, "soname", json_string(lib.soname.c_str()));
            json_object_set_new(obj, "build_id", json_string(lib.build_id.c_str()));
            json_array_append_new(libs_arr, obj);
        }
        json_object_set_new(root, "libraries", libs_arr);

        std::vector<std::pair<std::string, std::string>> parts;
        parts.reserve(summary.partitions.size());
        for (const auto& p : summary.partitions)
            parts.emplace_back(p.id, p.partition_hash);
        std::sort(parts.begin(), parts.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        json_t* parts_arr = json_array();
        for (const auto& ph : parts) {
            json_t* obj = json_object();
            json_object_set_new(obj, "id", json_string(ph.first.c_str()));
            json_object_set_new(obj, "hash", json_string(ph.second.c_str()));
            json_array_append_new(parts_arr, obj);
        }
        json_object_set_new(root, "partition_hashes", parts_arr);

        JsonHasher hasher(std::make_unique<DomainHasher<>>("summary"));
        hasher.add(root);
        json_decref(root);
        return hasher.hex();
    }

    std::string resolve_path(const std::string& base, const std::string& path) {
        if (path.empty() || path.front() == '/')
            return path;
        if (base.empty())
            return path;
        return (std::filesystem::path(base) / path).string();
    }

    PartitionInfo parse_partition(json_t* obj) {
        if (!json_is_object(obj))
            throw std::runtime_error("Partition invalide dans le summary");

        PartitionInfo info;
        info.id = to_string_safe(json_object_get(obj, "id"));
        info.asm_path = to_string_safe(json_object_get(obj, "asm"));
        info.bin_path = to_string_safe(json_object_get(obj, "bin"));
        info.wrapper_path = to_string_safe(json_object_get(obj, "wrapper"));
        info.bin_hash = to_string_safe(json_object_get(obj, "bin_hash"));
        info.partition_hash = to_string_safe(json_object_get(obj, "partition_hash"));
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

    void verify_hashes(const std::string& base_dir, PartitionSummary& summary) {
        if (!summary.binary_hash.empty()) {
            const auto computed = hash_file(resolve_path(base_dir, summary.binary_path));
            if (computed.empty() || computed != summary.binary_hash)
                throw std::runtime_error("Hash binaire invalide");
        }

        if (!summary.memory_hash.empty()) {
            const auto computed_mem = compute_memory_hash(summary.initial_memory);
            if (computed_mem != summary.memory_hash)
                throw std::runtime_error("Hash mémoire invalide");
            summary.memory_hash = computed_mem;
        }

        for (auto& p : summary.partitions) {
            if (!p.bin_hash.empty()) {
                const auto computed_bin = hash_file(resolve_path(base_dir, p.bin_path));
                if (computed_bin.empty() || computed_bin != p.bin_hash)
                    throw std::runtime_error("Hash binaire partition invalide pour " + p.id);
            }
            auto computed_part = compute_partition_hash(p);
            if (!p.partition_hash.empty() && p.partition_hash != computed_part)
                throw std::runtime_error("Hash partition invalide pour " + p.id);
            p.partition_hash = std::move(computed_part);
        }

        if (!summary.summary_hash.empty()) {
            const auto computed_summary = compute_summary_hash(summary);
            if (computed_summary != summary.summary_hash)
                throw std::runtime_error("Hash summary invalide");
        }
    }

    PartitionSummary parse_summary(json_t* root) {
        if (!json_is_object(root))
            throw std::runtime_error("Résumé invalide (racine)");

        PartitionSummary summary;
        summary.binary_path = to_string_safe(json_object_get(root, "binary"));
        summary.binary_hash = to_string_safe(json_object_get(root, "binary_hash"));
        summary.memory_hash = to_string_safe(json_object_get(root, "memory_hash"));
        summary.summary_hash = to_string_safe(json_object_get(root, "summary_hash"));
        if (json_t* can_split = json_object_get(root, "can_split"); json_is_boolean(can_split))
            summary.can_split = json_is_true(can_split);

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
            const std::string base_dir = std::filesystem::path(summary_path).parent_path().string();
            verify_hashes(base_dir, summary);
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
