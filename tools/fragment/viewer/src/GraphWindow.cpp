#include "GraphWindow.hpp"

#include <QFile>
#include <QJsonDocument>
#include <QJsonValue>
#include <QPen>
#include <QBrush>
#include <QGraphicsEllipseItem>
#include <QGraphicsTextItem>
#include <cmath>
#include <stdexcept>

namespace {

QColor NodeColor(bool parallel) {
    return parallel ? QColor(0, 180, 0) : QColor(200, 150, 0);
}

}  // namespace

GraphWindow::GraphWindow(const QString& summary_path, QWidget* parent)
    : QMainWindow(parent), scene_(new QGraphicsScene(this)), view_(new QGraphicsView(scene_)) {
    setWindowTitle("Fragment Graph Viewer");
    setCentralWidget(view_);
    view_->setRenderHint(QPainter::Antialiasing);
    view_->setDragMode(QGraphicsView::ScrollHandDrag);
    view_->setTransformationAnchor(QGraphicsView::AnchorUnderMouse);

    auto nodes = LoadSummary(summary_path);
    BuildGraph(nodes);
}

std::unordered_map<QString, GraphWindow::Node> GraphWindow::LoadSummary(const QString& path) const {
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
        auto deps = obj.value("dependencies");
        if (deps.isArray()) {
            for (const auto& d : deps.toArray())
                node.deps.push_back(d.toString());
        }
        nodes.emplace(node.id, std::move(node));
    }
    return nodes;
}

void GraphWindow::BuildGraph(const std::unordered_map<QString, Node>& nodes) {
    const double radius = 200.0;
    const double node_radius = 20.0;
    const int n = static_cast<int>(nodes.size());
    int idx = 0;

    // Positionner les nœuds en cercle simple.
    std::unordered_map<QString, QPointF> positions;
    for (const auto& pair : nodes) {
        double angle = (2 * M_PI * idx) / std::max(1, n);
        positions[pair.first] = QPointF(radius * std::cos(angle), radius * std::sin(angle));
        ++idx;
    }

    QPen edge_pen(Qt::gray);
    edge_pen.setWidth(2);

    for (const auto& pair : nodes) {
        const auto& node = pair.second;
        QPointF center = positions[node.id];
        QRectF ellipse(center.x() - node_radius, center.y() - node_radius, node_radius * 2, node_radius * 2);
        auto ellipse_item = scene_->addEllipse(ellipse, QPen(Qt::black), QBrush(NodeColor(node.parallel)));
        ellipse_item->setToolTip(QString("%1\n%2").arg(node.id).arg(node.parallel ? "Parallèle" : "Séquentiel"));

        auto text = scene_->addText(node.id);
        text->setPos(center.x() - node_radius, center.y() - node_radius - 20);
        text->setDefaultTextColor(Qt::black);

        for (const auto& dep : node.deps) {
            auto it = positions.find(dep);
            if (it == positions.end())
                continue;
            QPointF dst = it->second;
            auto line = scene_->addLine(QLineF(center, dst), edge_pen);
            line->setZValue(-1);
        }
    }

    view_->fitInView(scene_->itemsBoundingRect(), Qt::KeepAspectRatio);
}

