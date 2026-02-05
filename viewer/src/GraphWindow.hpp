#pragma once

#include <QGraphicsScene>
#include <QGraphicsView>
#include <QMainWindow>
#include <QString>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <optional>

#include "GraphModel.hpp"

class GraphWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit GraphWindow(const QString& summary_path, QWidget* parent = nullptr);
public slots:
    void UseCircularLayout();
    void UseTreeLayout();

private:
    QGraphicsScene* scene_;
    QGraphicsView* view_;
    GraphModel model_;
    std::unordered_map<QString, QPointF> positions_;

    QString BuildTooltip(const GraphModel::Node& node) const;
    void BuildGraph();
    void LayoutCircular();
    void LayoutTree();
    void ForceLayout(const std::vector<QString>& nodes, const std::vector<std::pair<QString, QString>>& edges,
                     const std::unordered_set<QString>& frozen = {});
    void DrawArrow(const QPointF& from, const QPointF& to, const QPen& pen, double node_radius, double head_length,
                   const std::optional<QPointF>& ctrl = std::nullopt);
    void DrawSelfLoop(const QPointF& center, const QPen& pen, double radius);
};
