#pragma once

#include <algorithm>
#include <iterator>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "core/Partition.hpp"
#include "partitioning/CallNormalizer.hpp"
#include "support/HashService.hpp"
#include "support/FlatMap.hpp"

namespace splitter {

using CallRef = std::pair<std::optional<uint64_t>, std::string>;
using CallMatrix = std::vector<std::vector<CallRef>>;

template <typename Normalizer = DefaultCallNormalizer>
class PartitionGraphBuilder {
public:
    explicit PartitionGraphBuilder(HashService hash_service = HashService())
        : hash_service_(std::move(hash_service)) {}

    void BuildGraph(std::vector<Partition>& partitions, const CallMatrix& call_refs) const;

private:
    void BuildIndices(const std::vector<Partition>& partitions,
                      FlatMap<uint64_t, size_t>& addr_index,
                      FlatMap<std::string, size_t>& id_index,
                      std::vector<std::set<std::string>>& parent_sets) const;
    void ResolveDependencies(std::vector<Partition>& partitions, const CallMatrix& call_refs,
                             const FlatMap<uint64_t, size_t>& addr_index,
                             std::vector<std::set<std::string>>& parent_sets) const;
    void AttachParents(std::vector<Partition>& partitions,
                       const std::vector<std::set<std::string>>& parent_sets) const;
    void CollectExternalCalls(std::vector<Partition>& partitions,
                              const CallMatrix& call_refs,
                              const FlatMap<uint64_t, size_t>& addr_index,
                              const FlatMap<std::string, size_t>& id_index) const;
    void ComputeExternalInputs(std::vector<Partition>& partitions,
                               const FlatMap<std::string, size_t>& id_index) const;

    Normalizer normalizer_;
    HashService hash_service_;
};

using DefaultPartitionGraphBuilder = PartitionGraphBuilder<DefaultCallNormalizer>;

}  // namespace splitter

// Template definitions
namespace splitter {

namespace detail {
inline std::string UnresolvedLabel(const CallRef& call) {
    if (!call.second.empty())
        return call.second;
    if (!call.first.has_value())
        return "[indirect call]";
    std::ostringstream oss;
    oss << "0x" << std::hex << call.first.value();
    return oss.str();
}
}  // namespace detail

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::BuildIndices(const std::vector<Partition>& partitions,
                                                     FlatMap<uint64_t, size_t>& addr_index,
                                                     FlatMap<std::string, size_t>& id_index,
                                                     std::vector<std::set<std::string>>& parent_sets) const {
    parent_sets.clear();
    parent_sets.resize(partitions.size());
    addr_index.clear();
    id_index.clear();
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        for (const auto& func : partitions[idx].Functions())
            addr_index[func.StartAddr()] = idx;
        id_index[partitions[idx].Id()] = idx;
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::ResolveDependencies(
    std::vector<Partition>& partitions, const CallMatrix& call_refs,
    const FlatMap<uint64_t, size_t>& addr_index,
    std::vector<std::set<std::string>>& parent_sets) const {
    auto short_name = [](const std::string& id) {
        auto first = id.find('_');
        if (first == std::string::npos)
            return id;
        auto second = id.find('_', first + 1);
        if (second == std::string::npos)
            return id.substr(first + 1);
        return id.substr(second + 1);
    };

    FlatMap<std::string, size_t> short_index;
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        short_index[short_name(partitions[idx].Id())] = idx;
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> dependency_set;
        std::set<std::string> unresolved_set;
        for (const auto& call : call_refs[idx]) {
            bool resolved = false;
            if (call.first.has_value()) {
                uint64_t target = call.first.value();
                auto it = addr_index.find(target);
                if (it != addr_index.end()) {
                    const std::string& child_id = partitions[it->second].Id();
                    dependency_set.insert(child_id);
                    if (child_id != partitions[idx].Id())
                        parent_sets[it->second].insert(partitions[idx].Id());
                    resolved = true;
                }
            }
            if (resolved)
                continue;

            auto symbol = normalizer_.Normalize(call);
            if (!symbol.empty()) {
                auto link = [&](const std::string& name) -> bool {
                    auto exact = short_index.find(name);
                    if (exact != short_index.end()) {
                        const std::string& child_id = partitions[exact->second].Id();
                        dependency_set.insert(child_id);
                        if (child_id != partitions[idx].Id())
                            parent_sets[exact->second].insert(partitions[idx].Id());
                        return true;
                    }
                    return false;
                };
                if (link(symbol))
                    continue;
                // Essayer sans préfixe func_xx_
                auto exact_id = short_name(symbol);
                if (link(exact_id))
                    continue;
            }

            unresolved_set.insert(detail::UnresolvedLabel(call));
        }
        partitions[idx].Dependencies().assign(dependency_set.begin(), dependency_set.end());
        partitions[idx].UnresolvedDependencies().assign(unresolved_set.begin(), unresolved_set.end());
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::AttachParents(
    std::vector<Partition>& partitions, const std::vector<std::set<std::string>>& parent_sets) const {
    for (size_t idx = 0; idx < partitions.size(); ++idx)
        partitions[idx].Parents().assign(parent_sets[idx].begin(), parent_sets[idx].end());
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::CollectExternalCalls(
    std::vector<Partition>& partitions, const CallMatrix& call_refs,
    const FlatMap<uint64_t, size_t>& addr_index,
    const FlatMap<std::string, size_t>& id_index) const {
    auto resolves_to_partition = [&](size_t idx, const CallRef& call) {
        if (!call.first.has_value())
            return false;
        auto it = addr_index.find(call.first.value());
        if (it == addr_index.end())
            return false;
        const auto& child_id = partitions[it->second].Id();
        (void)idx;
        return true;  // si l'adresse correspond à une partition, même self-call, ce n'est pas externe
    };

    auto short_name = [](const std::string& id) {
        auto first = id.find('_');
        if (first == std::string::npos)
            return id;
        auto second = id.find('_', first + 1);
        if (second == std::string::npos)
            return id.substr(first + 1);
        return id.substr(second + 1);
    };

    std::unordered_map<std::string, size_t> short_index;
    for (const auto& kv : id_index)
        short_index.emplace(short_name(kv.first), kv.second);

    auto find_partition = [&](const std::string& symbol) -> std::optional<size_t> {
        if (auto it = id_index.find(symbol); it != id_index.end())
            return it->second;
        if (auto sit = short_index.find(symbol); sit != short_index.end())
            return sit->second;
        return std::nullopt;
    };

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        FlatStringSet names;
        bool needs_display = false;
        for (const auto& call : call_refs[idx]) {
            if (resolves_to_partition(idx, call))
                continue;
            auto symbol = normalizer_.Normalize(call);
            if (!symbol.empty()) {
                if (auto target = find_partition(symbol)) {
                    const std::string& child_id = partitions[*target].Id();
                    partitions[idx].Dependencies().push_back(child_id);
                    if (*target != idx) {
                        auto& parents = partitions[*target].Parents();
                        if (std::find(parents.begin(), parents.end(), partitions[idx].Id()) == parents.end())
                            parents.push_back(partitions[idx].Id());
                    }
                    continue;
                }

                names.insert(symbol);
                if (!needs_display && normalizer_.IsGuiSymbol(symbol))
                    needs_display = true;
            }
        }
        partitions[idx].ExternalCalls() = std::move(names);
        partitions[idx].SetRequiresDisplay(needs_display);
        partitions[idx].SetBinHash(hash_service_.HashBytes(partitions[idx].RawBytes()));
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::ComputeExternalInputs(
    std::vector<Partition>& partitions, const FlatMap<std::string, size_t>& id_index) const {
    for (auto& partition : partitions) {
        FlatStringSet provided;
        for (const auto& parent_id : partition.Parents()) {
            auto it = id_index.find(parent_id);
            if (it == id_index.end())
                continue;
            const auto& outputs = partitions[it->second].Outputs();
            provided.insert(outputs.begin(), outputs.end());
        }
        FlatStringSet external;
        std::set_difference(partition.Inputs().begin(), partition.Inputs().end(),
                            provided.begin(), provided.end(),
                            std::inserter(external, external.begin()));
        partition.ExternalInputs() = external;
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::BuildGraph(std::vector<Partition>& partitions,
                                                   const CallMatrix& call_refs) const {
    FlatMap<uint64_t, size_t> addr_index;
    FlatMap<std::string, size_t> id_index;
    std::vector<std::set<std::string>> parent_sets;

    BuildIndices(partitions, addr_index, id_index, parent_sets);
    ResolveDependencies(partitions, call_refs, addr_index, parent_sets);
    AttachParents(partitions, parent_sets);
    CollectExternalCalls(partitions, call_refs, addr_index, id_index);
    // Chaînage runtime synthétique pour refléter le bootstrap CRT (_start/_init/ctors).
    auto short_name = [](const std::string& id) {
        auto first = id.find('_');
        if (first == std::string::npos)
            return id;
        auto second = id.find('_', first + 1);
        if (second == std::string::npos)
            return id.substr(first + 1);
        return id.substr(second + 1);
    };

    auto find_idx = [&](const std::string& suffix) -> std::optional<size_t> {
        for (size_t i = 0; i < partitions.size(); ++i) {
            if (partitions[i].Id() == suffix || short_name(partitions[i].Id()) == suffix)
                return i;
        }
        return std::nullopt;
    };

    auto add_edge = [&](size_t from, size_t to) {
        // Un edge signifie « from » doit être exécuté avant « to » (ordre logique).
        const auto& target_id = partitions[to].Id();
        auto& deps = partitions[from].Dependencies();
        if (std::find(deps.begin(), deps.end(), target_id) == deps.end())
            deps.push_back(target_id);
        auto& parents_vec = partitions[to].Parents();
        if (std::find(parents_vec.begin(), parents_vec.end(), partitions[from].Id()) == parents_vec.end())
            parents_vec.push_back(partitions[from].Id());
    };

    auto idx_start = find_idx("_start");
    auto idx_init = find_idx("_init");
    auto idx_rt = find_idx("register_tm_clones");
    auto idx_dereg = find_idx("deregister_tm_clones");
    auto idx_frame = find_idx("frame_dummy");
    auto idx_dtors = find_idx("__do_global_dtors_aux");
    auto idx_ctor = find_idx("_GLOBAL__sub_I_log_file");
    auto idx_fini = find_idx("_fini");
    std::vector<size_t> mains;
    for (size_t i = 0; i < partitions.size(); ++i)
        if (short_name(partitions[i].Id()) == "main")
            mains.push_back(i);

    // Chaînage : ordre d’exécution souhaité (bootstrap -> ctors -> main -> dtors).
    auto connect_seq = [&](const std::vector<size_t>& nodes) {
        for (size_t i = 1; i < nodes.size(); ++i)
            add_edge(nodes[i - 1], nodes[i]);
    };

    std::vector<size_t> prefix;
    if (idx_start) prefix.push_back(*idx_start);
    if (idx_init) prefix.push_back(*idx_init);
    if (idx_frame) prefix.push_back(*idx_frame);
    if (idx_rt) prefix.push_back(*idx_rt);
    if (idx_ctor) prefix.push_back(*idx_ctor);
    connect_seq(prefix);

    for (auto m : mains) {
        if (!prefix.empty())
            add_edge(prefix.back(), m);
        // Teardown : main -> dtors -> deregister -> _fini (dans cet ordre).
        size_t pivot = m;
        if (idx_dtors) {
            add_edge(pivot, *idx_dtors);
            pivot = *idx_dtors;
        }
        if (idx_dereg) {
            add_edge(pivot, *idx_dereg);
            pivot = *idx_dereg;
        }
        if (idx_fini)
            add_edge(pivot, *idx_fini);
    }

    // Post-traitement : si certains external_calls correspondent à des partitions connues
    // (nom complet ou suffixe), les reclasser en dépendances internes.
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        FlatStringSet remaining;
        for (const auto& sym : partitions[idx].ExternalCalls()) {
            bool matched = false;
            // Self-call par nom court
            if (sym == short_name(partitions[idx].Id())) {
                partitions[idx].Dependencies().push_back(partitions[idx].Id());
                matched = true;
            }
            for (size_t j = 0; j < partitions.size() && !matched; ++j) {
                const auto& cand = partitions[j].Id();
                if (cand == sym || short_name(cand) == sym) {
                    partitions[idx].Dependencies().push_back(cand);
                    if (j != idx) {
                        auto& parents = partitions[j].Parents();
                        if (std::find(parents.begin(), parents.end(), partitions[idx].Id()) == parents.end())
                            parents.push_back(partitions[idx].Id());
                    }
                    matched = true;
                }
            }
            if (!matched)
                remaining.insert(sym);
        }
        partitions[idx].ExternalCalls() = std::move(remaining);
    }

    // Supprimer les arêtes mutuelles directes (cycles à 2 nœuds) en conservant
    // l'arête depuis l'identifiant lexicographiquement le plus grand.
    FlatMap<std::string, size_t> id_lookup;
    for (size_t i = 0; i < partitions.size(); ++i)
        id_lookup[partitions[i].Id()] = i;

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        const auto& id = partitions[idx].Id();
        FlatStringSet pruned;
        for (const auto& dep : partitions[idx].Dependencies()) {
            auto it = id_lookup.find(dep);
            if (it != id_lookup.end()) {
                const auto& back_deps = partitions[it->second].Dependencies();
                const bool mutual = std::find(back_deps.begin(), back_deps.end(), id) != back_deps.end();
                if (mutual && id < dep)
                    continue;  // on garde seulement l'arête venant du plus grand id
            }
            pruned.insert(dep);
        }
        partitions[idx].Dependencies().assign(pruned.begin(), pruned.end());
    }
    ComputeExternalInputs(partitions, id_index);
}

}  // namespace splitter
