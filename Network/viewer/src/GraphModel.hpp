#pragma once

#include <QString>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string>

class GraphModel {
public:
    struct Node {
        QString id;
        bool parallel = false;
        std::vector<QString> deps;
        bool self_call = false;
        bool external = false;
        QString label;
        bool memory = false;
        QString start;
        QString end;
        int size = 0;
        std::vector<QString> inputs;
        std::vector<QString> outputs;
        std::vector<QString> external_inputs;
        std::vector<QString> external_calls;
        std::vector<QString> unresolved;
        std::vector<QString> required_libraries;
        QString bin_hash;
        QString partition_hash;
    };

    explicit GraphModel(const QString& summary_path);

    const std::unordered_map<QString, Node>& Nodes() const;
    const std::unordered_map<QString, std::vector<QString>>& Children() const;
    const std::unordered_set<std::string>& CycleEdges() const;
    const std::unordered_set<std::string>& CycleNodes() const;

    std::vector<QString> TopologicalOrder() const;
    bool HasReverseEdge(const QString& from, const QString& to) const;
    std::string EdgeKey(const QString& from, const QString& to) const;

private:
    std::unordered_map<QString, Node> LoadSummary(const QString& path) const;
    void BuildChildren();
    void DetectCycles();

    std::unordered_map<QString, Node> nodes_;
    std::unordered_map<QString, std::vector<QString>> children_;
    std::unordered_set<std::string> cycle_edges_;
    std::unordered_set<std::string> cycle_nodes_;
};
