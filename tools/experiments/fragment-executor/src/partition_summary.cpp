#include "fragment/partition_summary.hpp"

#include <fstream>
#include <queue>
#include <stdexcept>
#include <unordered_map>

#include "fragment/utils.hpp"

namespace fragment {

PartitionSummary load_partition_summary(const std::string& summary_path) {
    std::ifstream file(summary_path);
    if (!file) {
        throw std::runtime_error("Impossible d'ouvrir le fichier de résumé: " + summary_path);
    }
    std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());

    PartitionSummary summary;
    size_t partitions_pos = content.find("\"partitions\"");
    if (partitions_pos == std::string::npos) {
        throw std::runtime_error("Résumé invalide: champ \"partitions\" introuvable");
    }
    size_t array_start = content.find('[', partitions_pos);
    if (array_start == std::string::npos) {
        throw std::runtime_error("Résumé invalide: liste de partitions mal formée");
    }
    size_t array_end = find_matching(content, array_start, '[', ']');
    if (array_end == std::string::npos) {
        throw std::runtime_error("Résumé invalide: parenthèses non appariées");
    }

    size_t cursor = array_start;
    while (true) {
        size_t obj_start = content.find('{', cursor);
        if (obj_start == std::string::npos || obj_start > array_end) {
            break;
        }
        size_t obj_end = find_matching(content, obj_start, '{', '}');
        if (obj_end == std::string::npos) {
            throw std::runtime_error("Résumé invalide: accolades non appariées");
        }
        std::string object_text = content.substr(obj_start, obj_end - obj_start + 1);
        PartitionInfo info;
        info.id = extract_json_string(object_text, "id");
        info.asm_path = extract_json_string(object_text, "asm");
        info.bin_path = extract_json_string(object_text, "bin");
        info.wrapper_path = extract_json_string(object_text, "wrapper");
        info.parallelizable = extract_json_bool(object_text, "parallelizable", false);
        info.parents = extract_json_array(object_text, "parents");
        info.dependencies = extract_json_array(object_text, "dependencies");
        info.unresolved_calls = extract_json_array(object_text, "unresolved_calls");
        auto inputs_vec = extract_json_array(object_text, "inputs");
        info.inputs.insert(inputs_vec.begin(), inputs_vec.end());
        auto ext_inputs = extract_json_array(object_text, "external_inputs");
        info.external_inputs.insert(ext_inputs.begin(), ext_inputs.end());
        auto outputs_vec = extract_json_array(object_text, "outputs");
        info.outputs.insert(outputs_vec.begin(), outputs_vec.end());
        if (info.id.empty() || info.asm_path.empty()) {
            throw std::runtime_error("Résumé invalide: partition sans identifiant ou fichier ASM");
        }
        summary.partitions.push_back(std::move(info));
        cursor = obj_end + 1;
    }

    size_t binary_pos = content.find("\"binary\"");
    if (binary_pos != std::string::npos) {
        size_t colon = content.find(':', binary_pos);
        if (colon != std::string::npos) {
            size_t quote1 = content.find('"', colon);
            size_t quote2 = (quote1 != std::string::npos) ? content.find('"', quote1 + 1) : std::string::npos;
            if (quote1 != std::string::npos && quote2 != std::string::npos && quote2 > quote1) {
                summary.binary_path = content.substr(quote1 + 1, quote2 - quote1 - 1);
            }
        }
    }

    if (summary.partitions.empty()) {
        throw std::runtime_error("Résumé valide mais aucune partition trouvée");
    }
    return summary;
}

std::vector<std::string> order_partitions(const PartitionSummary& summary) {
    std::unordered_map<std::string, size_t> indegree;
    std::unordered_map<std::string, std::vector<std::string>> adjacency;
    for (const auto& partition : summary.partitions) {
        indegree[partition.id] = partition.parents.size();
        adjacency[partition.id];
    }
    std::unordered_map<std::string, const PartitionInfo*> info_by_id;
    for (const auto& partition : summary.partitions) {
        info_by_id[partition.id] = &partition;
        for (const auto& dep : partition.dependencies) {
            adjacency[partition.id].push_back(dep);
        }
    }

    std::priority_queue<std::string, std::vector<std::string>, std::greater<std::string>> ready;
    for (const auto& [id, degree] : indegree) {
        if (degree == 0) {
            ready.push(id);
        }
    }

    std::vector<std::string> order;
    while (!ready.empty()) {
        std::string current = ready.top();
        ready.pop();
        order.push_back(current);
        for (const auto& child : adjacency[current]) {
            auto it = indegree.find(child);
            if (it == indegree.end() || it->second == 0) continue;
            if (--it->second == 0) {
                ready.push(child);
            }
        }
    }

    if (order.size() != summary.partitions.size()) {
        throw std::runtime_error("Cycle détecté dans le graphe de partitions");
    }
    return order;
}

}  // namespace fragment
