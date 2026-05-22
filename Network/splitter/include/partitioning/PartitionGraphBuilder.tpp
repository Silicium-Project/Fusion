#pragma once

#include <sstream>
#include <unordered_map>

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
PartitionGraphBuilder<Normalizer>::PartitionGraphBuilder(HashService hash_service)
: normalizer_(), hash_service_(std::move(hash_service)) {}

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
    auto resolves_to_partition = [&](size_t /*idx*/, const CallRef& call) {
        if (!call.first.has_value())
            return false;
        auto it = addr_index.find(call.first.value());
        if (it == addr_index.end())
            return false;
        return true;
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
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::ComputeExternalInputs(
    std::vector<Partition>& partitions, const FlatMap<std::string, size_t>& id_index) const {
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

    for (auto& partition : partitions) {
        FlatStringSet inputs;
        for (const auto& dep : partition.Dependencies()) {
            auto find_partition = [&](const std::string& symbol) -> std::optional<size_t> {
                if (auto it = id_index.find(symbol); it != id_index.end())
                    return it->second;
                if (auto sit = short_index.find(symbol); sit != short_index.end())
                    return sit->second;
                return std::nullopt;
            };

            if (auto idx = find_partition(dep)) {
                const auto& child_inputs = partitions[*idx].Inputs();
                for (const auto& input : child_inputs)
                    inputs.insert(input);
            }
        }

        partition.ExternalInputs() = std::move(inputs);
    }
}

template <typename Normalizer>
void PartitionGraphBuilder<Normalizer>::BuildGraph(std::vector<Partition>& partitions,
                                                   const CallMatrix& call_refs) const {
    if (partitions.size() != call_refs.size())
        throw std::runtime_error("Incohérence partitions/call matrix");

    FlatMap<uint64_t, size_t> addr_index;
    FlatMap<std::string, size_t> id_index;
    std::vector<std::set<std::string>> parent_sets;

    BuildIndices(partitions, addr_index, id_index, parent_sets);
    ResolveDependencies(partitions, call_refs, addr_index, parent_sets);
    AttachParents(partitions, parent_sets);
    CollectExternalCalls(partitions, call_refs, addr_index, id_index);
    ComputeExternalInputs(partitions, id_index);
}

}  // namespace splitter
