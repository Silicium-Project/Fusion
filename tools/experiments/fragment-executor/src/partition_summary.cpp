#include "fragment/partition_summary.hpp"

#include <fstream>
#include <queue>
#include <stdexcept>
#include <unordered_map>

#include "fragment/utils.hpp"

namespace fragment {

using StringPair = std::pair<size_t, size_t>;
using Graph = std::unordered_map<std::string, std::vector<std::string>>;

static std::string read_summary_file(const std::string& path) {
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("Impossible d'ouvrir le fichier de résumé: " + path);
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

static StringPair locate_json_array(const std::string& content, const std::string& key) {
    size_t key_pos = content.find("\"" + key + "\"");
    if (key_pos == std::string::npos)
        throw std::runtime_error("Résumé invalide: champ \"" + key + "\" introuvable");

    size_t start = content.find('[', key_pos);
    if (start == std::string::npos)
        throw std::runtime_error("Résumé invalide: liste \"" + key + "\" mal formée");

    size_t end = find_matching(content, start, '[', ']');
    if (end == std::string::npos)
        throw std::runtime_error("Résumé invalide: parenthèses non appariées");

    return {start, end};
}

static bool next_object_slice(const std::string& content,
            size_t array_end, size_t& cursor, std::string& slice) {

    size_t obj_start = content.find('{', cursor);

    if (obj_start == std::string::npos || obj_start > array_end)
        return false;

    size_t obj_end = find_matching(content, obj_start, '{', '}');
    if (obj_end == std::string::npos)
        throw std::runtime_error("Résumé invalide: accolades non appariées");

    slice = content.substr(obj_start, obj_end - obj_start + 1);
    cursor = obj_end + 1;
    return true;
}

static PartitionInfo parse_partition_object(const std::string& object_text) {
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

    auto external_inputs = extract_json_array(object_text, "external_inputs");
    info.external_inputs.insert(external_inputs.begin(), external_inputs.end());

    auto outputs_vec = extract_json_array(object_text, "outputs");
    info.outputs.insert(outputs_vec.begin(), outputs_vec.end());

    if (info.id.empty() || info.asm_path.empty())
        throw std::runtime_error("Résumé invalide: partition sans identifiant ou fichier ASM");

    return info;
}

static void parse_partitions(const std::string& content, PartitionSummary& summary) {
    auto [array_start, array_end] = locate_json_array(content, "partitions");
    size_t cursor = array_start;
    std::string object_text;
    
    while (next_object_slice(content, array_end, cursor, object_text))
        summary.partitions.push_back(parse_partition_object(object_text));

    if (summary.partitions.empty())
        throw std::runtime_error("Résumé valide mais aucune partition trouvée");
}

static void parse_binary_path(const std::string& content, PartitionSummary& summary) {
    size_t binary_pos = content.find("\"binary\"");
    if (binary_pos == std::string::npos)
        return;

    size_t colon = content.find(':', binary_pos);
    if (colon == std::string::npos)
        return;

    size_t quote1 = content.find('"', colon);
    size_t quote2 = (quote1 != std::string::npos) ? content.find('"', quote1 + 1) : std::string::npos;
    if (quote1 == std::string::npos || quote2 == std::string::npos || quote2 <= quote1)
        return;

    summary.binary_path = content.substr(quote1 + 1, quote2 - quote1 - 1);
}

static Graph build_adjacency(const std::vector<PartitionInfo>& partitions,
                             std::unordered_map<std::string, size_t>& indegree) {
    Graph adjacency;

    for (const auto& partition : partitions) {
        indegree[partition.id] = partition.parents.size();
        adjacency[partition.id];
    }

    for (const auto& partition : partitions)
        for (const auto& dep : partition.dependencies)
            adjacency[partition.id].push_back(dep);

    return adjacency;
}

static std::priority_queue<std::string, std::vector<std::string>, std::greater<std::string>>
build_ready_queue(const std::unordered_map<std::string, size_t>& indegree) {
    std::priority_queue<std::string, std::vector<std::string>, std::greater<std::string>> ready;

    for (const auto& [id, degree] : indegree)
        if (degree == 0)
            ready.push(id);

    return ready;
}

static std::vector<std::string> order_partitions_impl(const std::vector<PartitionInfo>& partitions) {
    std::unordered_map<std::string, size_t> indegree;
    Graph adjacency = build_adjacency(partitions, indegree);
    auto ready = build_ready_queue(indegree);

    std::vector<std::string> order;
    order.reserve(partitions.size());

    while (!ready.empty()) {
        std::string current = ready.top();
        ready.pop();

        order.push_back(current);
        for (const auto& child : adjacency[current]) {
            auto it = indegree.find(child);
            if (it == indegree.end() || it->second == 0)
                continue;
            if (--it->second == 0)
                ready.push(child);
        }
    }

    if (order.size() != partitions.size())
        throw std::runtime_error("Cycle détecté dans le graphe de partitions");

    return order;
}

PartitionSummary load_partition_summary(const std::string& summary_path) {
    PartitionSummary summary;
    const std::string content = read_summary_file(summary_path);

    parse_partitions(content, summary);
    parse_binary_path(content, summary);
    return summary;
}

std::vector<std::string> order_partitions(const PartitionSummary& summary) {
    return order_partitions_impl(summary.partitions);
}

std::vector<std::string> order_partitions(const std::vector<PartitionInfo>& partitions) {
    return order_partitions_impl(partitions);
}

}  // namespace fragment
