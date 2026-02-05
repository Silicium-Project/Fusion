#include "GraphModel.hpp"

#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QDebug>

#include <algorithm>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>

GraphModel::GraphModel(const QString& summary_path)
    : nodes_(LoadSummary(summary_path)) {
    BuildChildren();
    DetectCycles();
}

const std::unordered_map<QString, GraphModel::Node>& GraphModel::Nodes() const {
    return nodes_;
}

const std::unordered_map<QString, std::vector<QString>>& GraphModel::Children() const {
    return children_;
}

const std::unordered_set<std::string>& GraphModel::CycleEdges() const {
    return cycle_edges_;
}

const std::unordered_set<std::string>& GraphModel::CycleNodes() const {
    return cycle_nodes_;
}

std::unordered_map<QString, GraphModel::Node> GraphModel::LoadSummary(const QString& path) const {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        throw std::runtime_error("Impossible d'ouvrir le summary: " + path.toStdString());

    auto doc = QJsonDocument::fromJson(file.readAll());
    if (!doc.isObject())
        throw std::runtime_error("Summary JSON invalide");

    QJsonObject root = doc.object();
    auto partitions_val = root.value("partitions");
    if (!partitions_val.isArray())
        throw std::runtime_error("Champ 'partitions' manquant");

    std::unordered_map<QString, Node> nodes;
    for (const auto& item : partitions_val.toArray()) {
        if (!item.isObject())
            continue;
        QJsonObject obj = item.toObject();
        Node node;
        node.id = obj.value("id").toString();
        node.parallel = obj.value("is_parallelizable").toBool(false);
        node.start = obj.value("start").toString();
        node.end = obj.value("end").toString();
        node.size = obj.value("size").toInt();
        node.label = node.id;
        auto deps = obj.value("dependencies");
        if (deps.isArray()) {
            for (const auto& d : deps.toArray())
                node.deps.push_back(d.toString());
        }
        auto ext_calls = obj.value("external_calls");
        if (ext_calls.isArray()) {
            for (const auto& c : ext_calls.toArray()) {
                QString call = c.toString();
                node.external_calls.push_back(call);
                // Typical case: id="func_9_transform", external call "transform".
                if (call == node.id)
                    node.self_call = true;
                else {
                    int idx = node.id.indexOf('_');
                    idx = node.id.indexOf('_', idx + 1);
                    if (idx != -1) {
                        QString short_name = node.id.mid(idx + 1);
                        if (call == short_name)
                            node.self_call = true;
                    }
                }
            }
        }
        auto unresolved_calls = obj.value("unresolved_calls");
        if (unresolved_calls.isArray())
            for (const auto& c : unresolved_calls.toArray())
                node.unresolved.push_back(c.toString());
        auto required_libs = obj.value("required_libraries");
        if (required_libs.isArray())
            for (const auto& l : required_libs.toArray())
                node.required_libraries.push_back(l.toString());
        auto inputs = obj.value("inputs");
        if (inputs.isArray())
            for (const auto& i : inputs.toArray())
                node.inputs.push_back(i.toString());
        auto outputs = obj.value("outputs");
        if (outputs.isArray())
            for (const auto& i : outputs.toArray())
                node.outputs.push_back(i.toString());
        auto ext_inputs = obj.value("external_inputs");
        if (ext_inputs.isArray())
            for (const auto& i : ext_inputs.toArray())
                node.external_inputs.push_back(i.toString());
        node.bin_hash = obj.value("bin_hash").toString();
        node.partition_hash = obj.value("partition_hash").toString();
        nodes.emplace(node.id, std::move(node));
    }

    // Insert external calls as dedicated nodes.
    for (const auto& item : partitions_val.toArray()) {
        if (!item.isObject())
            continue;
        QJsonObject obj = item.toObject();
        QString caller = obj.value("id").toString();
        auto ext_calls = obj.value("external_calls");
        auto unresolved = obj.value("unresolved_calls");
        auto part_libs = obj.value("required_libraries");
        auto process_libs = [&](const QJsonArray& arr) {
            for (const auto& l : arr) {
                QString name = l.toString();
                QString lib_id = "lib:" + name;
                if (!nodes.count(lib_id)) {
                    Node lib;
                    lib.id = lib_id;
                    lib.label = name;
                    lib.external = true;
                    nodes.emplace(lib_id, std::move(lib));
                }
                nodes[caller].deps.push_back(lib_id);
            }
        };
        auto process_list = [&](const QJsonArray& arr) {
            for (const auto& c : arr) {
                QString name = c.toString();
                // If the target matches a known partition (full id or suffix), link internally.
                bool linked_internal = false;
                if (nodes.count(name)) {
                    nodes[caller].deps.push_back(name);
                    linked_internal = true;
                } else {
                    int idx = name.indexOf('_');
                    idx = name.indexOf('_', idx + 1);
                    QString short_name = (idx != -1) ? name.mid(idx + 1) : name;
                    for (const auto& kv : nodes) {
                        QString target_short = kv.first;
                        int idx2 = target_short.indexOf('_');
                        idx2 = target_short.indexOf('_', idx2 + 1);
                        if (idx2 != -1)
                            target_short = target_short.mid(idx2 + 1);
                        if (target_short == short_name) {
                            nodes[caller].deps.push_back(kv.first);
                            linked_internal = true;
                            break;
                        }
                    }
                }
                if (linked_internal)
                    continue;

                QString ext_id = "ext:" + name;
                if (!nodes.count(ext_id)) {
                    Node ext;
                    ext.id = ext_id;
                    ext.label = name;
                    ext.external = true;
                    nodes.emplace(ext_id, std::move(ext));
                }
                nodes[caller].deps.push_back(ext_id);
            }
        };
        if (ext_calls.isArray())
            process_list(ext_calls.toArray());
        if (unresolved.isArray())
            process_list(unresolved.toArray());
        if (part_libs.isArray())
            process_libs(part_libs.toArray());
    }

    // Summary-level libraries.
    auto libs_val = root.value("required_libraries");
    if (libs_val.isArray()) {
        for (const auto& l : libs_val.toArray()) {
            QString name = l.toString();
            QString lib_id = "lib:" + name;
            if (!nodes.count(lib_id)) {
                Node lib;
                lib.id = lib_id;
                lib.label = name;
                lib.external = true;
                nodes.emplace(lib_id, std::move(lib));
            }
        }
    }

    // Global memory node.
    Node mem;
    mem.id = "memory";
    mem.label = "Memory";
    mem.external = true;
    mem.memory = true;
    mem.partition_hash = root.value("memory_hash").toString();
    nodes.emplace(mem.id, std::move(mem));
    for (auto& kv : nodes) {
        if (kv.second.memory)
            continue;
        kv.second.deps.push_back("memory");
    }

    return nodes;
}

void GraphModel::BuildChildren() {
    children_.clear();
    for (const auto& pair : nodes_) {
        for (const auto& dep : pair.second.deps)
            children_[pair.first].push_back(dep);
    }
}

void GraphModel::DetectCycles() {
    cycle_edges_.clear();
    cycle_nodes_.clear();
    for (const auto& kv : nodes_) {
        if (kv.second.self_call) {
            cycle_nodes_.insert(kv.first.toStdString());
            cycle_edges_.insert(EdgeKey(kv.first, kv.first));
            qDebug() << "[viewer] Auto-appel detecte pour" << kv.first;
        }
    }
    std::unordered_map<QString, int> index;
    std::unordered_map<QString, int> lowlink;
    std::unordered_map<QString, bool> on_stack;
    std::vector<QString> stack;
    int current_index = 0;

    std::function<void(const QString&)> dfs = [&](const QString& u) {
        index[u] = lowlink[u] = current_index++;
        stack.push_back(u);
        on_stack[u] = true;

        auto it = children_.find(u);
        if (it != children_.end()) {
            for (const auto& v : it->second) {
                if (!index.count(v)) {
                    dfs(v);
                    lowlink[u] = std::min(lowlink[u], lowlink[v]);
                } else if (on_stack[v]) {
                    lowlink[u] = std::min(lowlink[u], index[v]);
                }
            }
        }

        if (lowlink[u] == index[u]) {
            std::vector<QString> scc;
            while (true) {
                QString w = stack.back();
                stack.pop_back();
                on_stack[w] = false;
                scc.push_back(w);
                if (w == u)
                    break;
            }

            const bool self_loop = scc.size() == 1 && HasReverseEdge(scc.front(), scc.front());
            if (scc.size() > 1 || self_loop) {
                qDebug() << "[viewer] SCC detecte:" << scc << "self_loop?" << self_loop;
                for (const auto& n : scc)
                    cycle_nodes_.insert(n.toStdString());
                for (const auto& n : scc) {
                    const auto& node = nodes_.at(n);
                    for (const auto& d : node.deps) {
                        if (std::find(scc.begin(), scc.end(), d) != scc.end()) {
                            cycle_edges_.insert(EdgeKey(d, n));
                            qDebug() << "[viewer]   arete cycle" << d << "->" << n;
                        }
                    }
                }
            }
        }
    };

    for (const auto& pair : nodes_) {
        if (!index.count(pair.first))
            dfs(pair.first);
    }
}

std::vector<QString> GraphModel::TopologicalOrder() const {
    std::map<QString, int> indegree;
    for (const auto& pair : nodes_) {
        if (!pair.second.external)
            indegree[pair.first] = 0;
    }
    for (const auto& pair : nodes_) {
        if (pair.second.external)
            continue;
        for (const auto& dep : pair.second.deps) {
            auto it = indegree.find(dep);
            if (it != indegree.end())
                it->second++;
        }
    }

    std::multiset<QString> ready;
    for (const auto& kv : indegree) {
        if (kv.second == 0)
            ready.insert(kv.first);
    }

    std::vector<QString> order;
    while (!ready.empty()) {
        auto it = ready.begin();
        QString id = *it;
        ready.erase(it);
        order.push_back(id);

        auto child_it = children_.find(id);
        if (child_it == children_.end())
            continue;
        for (const auto& succ : child_it->second) {
            auto d_it = indegree.find(succ);
            if (d_it == indegree.end())
                continue;
            d_it->second--;
            if (d_it->second == 0)
                ready.insert(succ);
        }
    }

    if (order.size() != nodes_.size()) {
        for (const auto& kv : indegree) {
            if (std::find(order.begin(), order.end(), kv.first) == order.end())
                order.push_back(kv.first);
        }
    }
    return order;
}

bool GraphModel::HasReverseEdge(const QString& from, const QString& to) const {
    auto it = nodes_.find(to);
    if (it == nodes_.end())
        return false;
    return std::find(it->second.deps.begin(), it->second.deps.end(), from) != it->second.deps.end();
}

std::string GraphModel::EdgeKey(const QString& from, const QString& to) const {
    return from.toStdString() + "->" + to.toStdString();
}
