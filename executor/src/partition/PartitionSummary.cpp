#include "partition/PartitionSummary.hpp"

#include <jansson.h>

#include <queue>
#include <unordered_map>
#include <fstream>
#include <functional>
#include <cstdint>
#include <cctype>
#include <sstream>
#include <algorithm>
#include <iomanip>
#include <filesystem>

#include "support/Utils.hpp"
#include "support/Hash.hpp"
#include "support/JsonHasher.hpp"

namespace fragment {

    namespace {

    uint32_t parse_schema_version(json_t* root,
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

    std::string normalize_algo(std::string algo) {
        if (algo.empty())
            return "fnv";
        std::transform(algo.begin(), algo.end(), algo.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (algo == "std" || algo == "fnv")
            return algo;
        return "fnv";
    }

    std::unique_ptr<Hasher> make_hasher(const std::string& algo) {
        const auto normalized = normalize_algo(algo);
        if (normalized == "std")
            return std::make_unique<StdHasher>();
        return std::make_unique<FnvHasher>();
    }

    std::string hash_bytes(const std::vector<uint8_t>& data, const std::string& algo) {
        auto h = make_hasher(algo);
        for (auto b : data)
            h->add_byte(b);
        return h->hex();
    }

    std::string hash_file(const std::string& path, const std::string& algo) {
        std::ifstream file(path, std::ios::binary);
        if (!file.is_open())
            return {};
        std::vector<uint8_t> buffer((std::istreambuf_iterator<char>(file)),
                                    std::istreambuf_iterator<char>());
        return hash_bytes(buffer, algo);
    }

    std::string compute_partition_hash(const PartitionInfo& p, const std::string& algo) {
        auto hasher = make_hasher(algo);
        hasher->reset();
        hasher->add_string(p.id);
        if (!p.os.empty())
            hasher->add_string(p.os);
        if (!p.format.empty())
            hasher->add_string(p.format);
        hasher->add_uint64(p.start_address.value_or(0));
        hasher->add_uint64(p.end_address.value_or(0));
        hasher->add_string(p.bin_hash);
        hasher->add_uint64(p.binary_size);
        hasher->add_bool(p.parallelizable);
        hasher->add_bool(p.requires_display);

        auto hash_strings = [&](const auto& container) {
            for (const auto& s : container)
                hasher->add_string(s);
            hasher->add_byte(0x7f);
        };

        hash_strings(p.inputs);
        hash_strings(p.external_inputs);
        hash_strings(p.outputs);
        hash_strings(p.external_calls);
        hash_strings(p.required_libraries);
        hash_strings(p.parents);
        hash_strings(p.dependencies);
        hash_strings(p.unresolved_calls);

        return hasher->hex();
    }

    std::string compute_memory_hash(const std::vector<MemoryRegion>& segments, const std::string& algo) {
        auto hasher = make_hasher(algo);
        hasher->reset();
        for (const auto& seg : segments) {
            hasher->add_string(seg.name);
            hasher->add_uint64(seg.address);
            hasher->add_string(hash_bytes(seg.bytes, algo));
        }
        return hasher->hex();
    }

    std::string compute_summary_hash(const PartitionSummary& summary) {
        auto hasher = make_hasher(summary.hash_algo);
        hasher->reset();
        if (!summary.binary_os.empty())
            hasher->add_string(summary.binary_os);
        if (!summary.binary_format.empty())
            hasher->add_string(summary.binary_format);
        hasher->add_string(summary.binary_hash);
        hasher->add_string(summary.memory_hash);
        hasher->add_bool(summary.can_split);

        auto required = summary.required_libraries;
        std::sort(required.begin(), required.end());
        for (const auto& r : required)
            hasher->add_string(r);
        hasher->add_byte(0x7f);

        auto libs = summary.libraries;
        std::sort(libs.begin(), libs.end(), [](const auto& a, const auto& b) { return a.name < b.name; });
        for (const auto& lib : libs) {
            hasher->add_string(lib.name);
            hasher->add_string(lib.path);
            hasher->add_string(lib.soname.empty() ? lib.name : lib.soname);
            hasher->add_string(lib.build_id);
        }

        std::vector<std::pair<std::string, std::string>> parts;
        parts.reserve(summary.partitions.size());
        for (const auto& p : summary.partitions)
            parts.emplace_back(p.id, p.partition_hash);
        std::sort(parts.begin(), parts.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        for (const auto& ph : parts) {
            hasher->add_string(ph.first);
            hasher->add_string(ph.second);
        }

        return hasher->hex();
    }

    std::string resolve_path(const std::string& base, const std::string& path) {
        if (path.empty() || path.front() == '/')
            return path;
        if (base.empty())
            return path;

        auto normalize = [](const std::filesystem::path& p) {
            return std::filesystem::absolute(p).lexically_normal();
        };

        std::filesystem::path probe = base;
        std::filesystem::path rel(path);

        // Remonter la hiérarchie jusqu'à trouver un chemin existant.
        while (true) {
            std::filesystem::path candidate = normalize(probe / rel);
            if (std::filesystem::exists(candidate))
                return candidate.string();
            if (!probe.has_parent_path())
                break;
            const std::filesystem::path parent = probe.parent_path();
            if (parent == probe)
                break;
            probe = parent;
        }

        if (std::filesystem::exists(rel))
            return normalize(rel).string();

        // Fallback : chemin normalisé relatif au base d'origine.
        return (normalize(base) / rel).string();
    }

    PartitionInfo parse_partition(json_t* obj) {
        if (!json_is_object(obj))
            throw std::runtime_error("Partition invalide dans le summary");

        PartitionInfo info;
        info.id = to_string_safe(json_object_get(obj, "id"));
        info.asm_path = to_string_safe(json_object_get(obj, "asm"));
        info.bin_path = to_string_safe(json_object_get(obj, "bin"));
        info.wrapper_path = to_string_safe(json_object_get(obj, "wrapper"));
        info.os = to_string_safe(json_object_get(obj, "os"));
        info.format = to_string_safe(json_object_get(obj, "format"));
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

    void verify_hashes(const std::string& base_dir, PartitionSummary& summary, bool skip_memory_check) {
        const bool skip_all_hash = std::getenv("SKIP_HASH") != nullptr;

        if (skip_memory_check || skip_all_hash) {
            if (!summary.memory_hash.empty())
                summary.memory_hash = compute_memory_hash(summary.initial_memory, summary.hash_algo);
        } else {
            if (!summary.binary_hash.empty()) {
                const auto computed = hash_file(resolve_path(base_dir, summary.binary_path), summary.hash_algo);
                if (computed.empty() || computed != summary.binary_hash)
                    throw std::runtime_error("Hash binaire invalide");
            }

            if (!summary.memory_hash.empty()) {
                const auto computed_mem = compute_memory_hash(summary.initial_memory, summary.hash_algo);
                if (computed_mem != summary.memory_hash)
                    throw std::runtime_error("Hash mémoire invalide");
                summary.memory_hash = computed_mem;
            }
        }

        for (auto& p : summary.partitions) {
            auto computed_part = compute_partition_hash(p, summary.hash_algo);
            if (p.partition_hash.empty())
                p.partition_hash = computed_part;
            const bool skip_bin_check = skip_memory_check || skip_all_hash || p.binary_size == 0;
            if (!skip_bin_check && p.bin_hash.size() > 0) {
                const auto computed_bin = hash_file(resolve_path(base_dir, p.bin_path), summary.hash_algo);
                if (computed_bin.empty() || computed_bin != p.bin_hash)
                    throw std::runtime_error("Hash binaire partition invalide pour " + p.id);
            }
        }

        if (!summary.summary_hash.empty()) {
            const auto computed_summary = compute_summary_hash(summary);
            if (!skip_all_hash && computed_summary != summary.summary_hash)
                throw std::runtime_error("Hash summary invalide");
            summary.summary_hash = computed_summary;
        }
    }

    PartitionSummary parse_summary(json_t* root) {
        if (!json_is_object(root))
            throw std::runtime_error("Résumé invalide (racine)");

        PartitionSummary summary;
        summary.schema_version = parse_schema_version(
            root, "schema_version", kPartitionSummarySchemaVersion, "summary");
        summary.binary_path = to_string_safe(json_object_get(root, "binary"));
        summary.binary_os = to_string_safe(json_object_get(root, "binary_os"));
        summary.binary_format = to_string_safe(json_object_get(root, "binary_format"));
        summary.binary_hash = to_string_safe(json_object_get(root, "binary_hash"));
        summary.hash_algo = normalize_algo(to_string_safe(json_object_get(root, "hash_algo")));
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
        for (const auto& partition : partitions) {
            for (const auto& dep : partition.dependencies) {
                if (dep == partition.id)
                    continue;  // ignorer les self-loops pour l'ordre topo
                adjacency[partition.id].push_back(dep);
            }
        }

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

    PartitionSummary load_partition_summary(const std::string& summary_path, bool skip_memory_check) {
        json_error_t error;
        json_t* root = json_load_file(summary_path.c_str(), 0, &error);
        if (!root)
            throw std::runtime_error("Impossible de parser le summary: " + std::string(error.text));
        PartitionSummary summary;
        try {
            summary = parse_summary(root);
            const std::string base_dir = std::filesystem::path(summary_path).parent_path().string();
            for (auto& p : summary.partitions) {
                p.asm_path = resolve_path(base_dir, p.asm_path);
                p.bin_path = resolve_path(base_dir, p.bin_path);
                p.wrapper_path = resolve_path(base_dir, p.wrapper_path);
            }
            summary.binary_path = resolve_path(base_dir, summary.binary_path);
            verify_hashes(base_dir, summary, skip_memory_check);
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
