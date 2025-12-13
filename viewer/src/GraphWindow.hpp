#pragma once

#include <QGraphicsScene>
#include <QGraphicsView>
#include <QMainWindow>
#include <QJsonObject>
#include <QJsonArray>
#include <QString>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string>
#include <optional>

class GraphWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit GraphWindow(const QString& summary_path, QWidget* parent = nullptr);
public slots:
    void UseCircularLayout();
    void UseTreeLayout();

private:
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

    QGraphicsScene* scene_;
    QGraphicsView* view_;
    std::unordered_map<QString, Node> nodes_;
    std::unordered_map<QString, QPointF> positions_;
    std::unordered_set<std::string> cycle_edges_;
    std::unordered_set<std::string> cycle_nodes_;

    std::unordered_map<QString, Node> LoadSummary(const QString& path) const;
    std::unordered_map<QString, std::vector<QString>> BuildChildren() const;
    void DetectCycles(const std::unordered_map<QString, std::vector<QString>>& children);
    std::vector<QString> TopologicalOrder(const std::unordered_map<QString, std::vector<QString>>& children) const;
    bool HasReverseEdge(const QString& from, const QString& to) const;
    std::string EdgeKey(const QString& from, const QString& to) const;
    QString BuildTooltip(const Node& node) const;
    void BuildGraph();
    void LayoutCircular();
    void LayoutTree();
    void ForceLayout(const std::vector<QString>& nodes, const std::vector<std::pair<QString, QString>>& edges,
                     const std::unordered_set<QString>& frozen = {});
    void DrawArrow(const QPointF& from, const QPointF& to, const QPen& pen, double node_radius, double head_length,
                   const std::optional<QPointF>& ctrl = std::nullopt);
    void DrawSelfLoop(const QPointF& center, const QPen& pen, double radius);
};
