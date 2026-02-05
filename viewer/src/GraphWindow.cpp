#include "GraphWindow.hpp"

#include <QAction>
#include <QBrush>
#include <QDebug>
#include <QGraphicsEllipseItem>
#include <QGraphicsPolygonItem>
#include <QGraphicsTextItem>
#include <QLineF>
#include <QPainterPath>
#include <QPen>
#include <QPolygonF>
#include <QStringList>
#include <QToolBar>

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>

namespace {

QColor NodeColor(bool parallel, bool external, bool memory) {
    if (memory)
        return QColor(160, 120, 200);
    if (external)
        return QColor(90, 140, 200);
    return parallel ? QColor(0, 180, 0) : QColor(200, 150, 0);
}

}  // namespace

GraphWindow::GraphWindow(const QString& summary_path, QWidget* parent)
    : QMainWindow(parent),
      scene_(new QGraphicsScene(this)),
      view_(new QGraphicsView(scene_)),
      model_(summary_path) {
    setWindowTitle("Fragment Graph Viewer");
    setCentralWidget(view_);
    view_->setRenderHint(QPainter::Antialiasing);
    view_->setDragMode(QGraphicsView::ScrollHandDrag);
    view_->setTransformationAnchor(QGraphicsView::AnchorUnderMouse);

    auto* toolbar = addToolBar("Layout");
    auto* circleAction = toolbar->addAction("Cercle");
    auto* treeAction = toolbar->addAction("Arborescence");
    connect(circleAction, &QAction::triggered, this, &GraphWindow::UseCircularLayout);
    connect(treeAction, &QAction::triggered, this, &GraphWindow::UseTreeLayout);

    LayoutCircular();
}

void GraphWindow::BuildGraph() {
    scene_->clear();
    const double node_radius = 22.0;
    const double arrow_head = 16.0;
    QPen edge_pen(Qt::gray);
    edge_pen.setWidth(2);

    const auto& nodes = model_.Nodes();
    auto order = model_.TopologicalOrder();
    if (order.empty()) {
        order.reserve(nodes.size());
        for (const auto& pair : nodes)
            order.push_back(pair.first);
    }
    std::unordered_map<QString, int> order_index;
    for (int i = 0; i < static_cast<int>(order.size()); ++i)
        order_index[order[i]] = i + 1;

    std::vector<QString> draw_ids = order;
    for (const auto& kv : nodes) {
        if (std::find(draw_ids.begin(), draw_ids.end(), kv.first) == draw_ids.end())
            draw_ids.push_back(kv.first);
    }

    const auto& cycle_nodes = model_.CycleNodes();
    const auto& cycle_edges = model_.CycleEdges();

    for (const auto& id : draw_ids) {
        const auto& node = nodes.at(id);
        QPointF center = positions_[node.id];
        QRectF ellipse(center.x() - node_radius, center.y() - node_radius, node_radius * 2, node_radius * 2);
        QPen node_pen(Qt::black);
        const bool is_cycle = cycle_nodes.count(node.id.toStdString()) > 0;
        if (is_cycle)
            node_pen.setColor(Qt::red);
        auto ellipse_item = scene_->addEllipse(
            ellipse, node_pen, QBrush(NodeColor(node.parallel, node.external, node.memory)));
        ellipse_item->setToolTip(BuildTooltip(node));

        QString label = node.label.isEmpty() ? node.id : node.label;
        auto idx_it = order_index.find(node.id);
        if (idx_it != order_index.end())
            label = QString::number(idx_it->second) + " - " + label;
        if (is_cycle)
            label += " [cycle]";
        auto text = scene_->addText(label);
        text->setPos(center.x() - node_radius, center.y() - node_radius - 24);
        text->setRotation(-20);
        text->setDefaultTextColor(Qt::black);

        bool has_self_loop = false;
        for (const auto& dep : node.deps) {
            if (dep == node.id) {
                QPen loop_pen(Qt::red);
                loop_pen.setWidth(2);
                loop_pen.setStyle(Qt::DashLine);
                DrawSelfLoop(center, loop_pen, node_radius);
                has_self_loop = true;
                continue;
            }
            const bool is_memory_edge = dep == "memory";
            auto it = positions_.find(dep);
            if (it == positions_.end())
                continue;
            QPointF dep_pos = it->second;
            const bool in_cycle = cycle_edges.count(model_.EdgeKey(dep, node.id)) > 0;
            QPen pen = in_cycle ? QPen(Qt::red) : edge_pen;
            pen.setWidth(is_memory_edge ? 1 : (in_cycle ? 3 : 2));
            pen.setStyle(is_memory_edge ? Qt::DotLine : (in_cycle ? Qt::DashLine : Qt::SolidLine));

            std::optional<QPointF> ctrl;
            const bool bidirectional = model_.HasReverseEdge(node.id, dep);
            if (bidirectional) {
                QLineF base(center, dep_pos);
                if (base.length() > 1.0) {
                    QPointF mid = (dep_pos + center) / 2.0;
                    QPointF perp = QPointF(-(dep_pos.y() - center.y()), dep_pos.x() - center.x());
                    double norm = std::sqrt(perp.x() * perp.x() + perp.y() * perp.y());
                    if (norm > 0.1) {
                        perp /= norm;
                        double bend = 60.0;
                        double sign = node.id < dep ? 1.0 : -1.0;
                        ctrl = mid + perp * bend * sign;
                    }
                }
            }

            DrawArrow(center, dep_pos, pen, node_radius, arrow_head, ctrl);
        }

        if (!has_self_loop && (cycle_nodes.count(node.id.toStdString()) || node.self_call)) {
            QPen loop_pen(Qt::red);
            loop_pen.setWidth(2);
            loop_pen.setStyle(Qt::DashLine);
            DrawSelfLoop(center, loop_pen, node_radius);
        }
    }

    view_->fitInView(scene_->itemsBoundingRect(), Qt::KeepAspectRatio);
}

QString GraphWindow::BuildTooltip(const GraphModel::Node& node) const {
    QStringList lines;
    lines << node.label;
    if (!node.start.isEmpty())
        lines << QString("Adresse: %1 - %2 (%3 o)").arg(node.start, node.end).arg(node.size);
    if (!node.inputs.empty())
        lines << "Entrees: " + QStringList(node.inputs.begin(), node.inputs.end()).join(", ");
    if (!node.outputs.empty())
        lines << "Sorties: " + QStringList(node.outputs.begin(), node.outputs.end()).join(", ");
    if (!node.external_inputs.empty())
        lines << "Entrees externes: " + QStringList(node.external_inputs.begin(), node.external_inputs.end()).join(", ");
    if (!node.external_calls.empty())
        lines << "Appels externes: " + QStringList(node.external_calls.begin(), node.external_calls.end()).join(", ");
    if (!node.unresolved.empty())
        lines << "Appels inconnus: " + QStringList(node.unresolved.begin(), node.unresolved.end()).join(", ");
    if (!node.required_libraries.empty())
        lines << "Libs: " + QStringList(node.required_libraries.begin(), node.required_libraries.end()).join(", ");
    if (!node.bin_hash.isEmpty())
        lines << "bin_hash: " + node.bin_hash;
    if (!node.partition_hash.isEmpty())
        lines << "part_hash: " + node.partition_hash;
    if (node.memory)
        lines << "Memoire globale";
    if (node.external)
        lines << "Externe";
    return lines.join("\n");
}

void GraphWindow::LayoutCircular() {
    const double radius = 250.0;
    positions_.clear();
    const QString memory_id = "memory";
    const auto& nodes = model_.Nodes();
    auto order = model_.TopologicalOrder();
    if (order.empty()) {
        order.reserve(nodes.size());
        for (const auto& pair : nodes)
            order.push_back(pair.first);
    }
    const int n = static_cast<int>(order.size());
    for (int idx = 0; idx < n; ++idx) {
        double angle = (2 * M_PI * idx) / std::max(1, n);
        positions_[order[idx]] = QPointF(radius * std::cos(angle), radius * std::sin(angle));
    }
    int extra = n;
    for (const auto& kv : nodes) {
        if (positions_.count(kv.first))
            continue;
        double angle = (2 * M_PI * extra) / std::max(1, static_cast<int>(nodes.size()));
        positions_[kv.first] = QPointF(radius * std::cos(angle), radius * std::sin(angle));
        ++extra;
    }

    std::vector<std::pair<QString, QString>> edges;
    for (const auto& pair : nodes) {
        for (const auto& dep : pair.second.deps)
            edges.emplace_back(pair.first, dep);
    }
    std::vector<QString> all_ids;
    all_ids.reserve(nodes.size());
    for (const auto& kv : nodes)
        all_ids.push_back(kv.first);
    std::unordered_set<QString> frozen;
    if (positions_.count(memory_id))
        frozen.insert(memory_id);
    ForceLayout(all_ids, edges, frozen);

    if (positions_.count(memory_id)) {
        double max_r = radius + 200;
        positions_[memory_id] = QPointF(max_r, -max_r * 0.3);
    }

    BuildGraph();
}

void GraphWindow::LayoutTree() {
    positions_.clear();
    const auto& nodes = model_.Nodes();
    auto order = model_.TopologicalOrder();
    if (order.empty()) {
        order.reserve(nodes.size());
        for (const auto& pair : nodes)
            order.push_back(pair.first);
    }

    std::unordered_map<QString, std::vector<QString>> parents;
    for (const auto& pair : nodes) {
        for (const auto& dep : pair.second.deps)
            parents[dep].push_back(pair.first);
    }

    std::unordered_map<QString, int> level;
    for (const auto& id : order) {
        int lvl = 0;
        auto p_it = parents.find(id);
        if (p_it != parents.end()) {
            for (const auto& par : p_it->second) {
                auto lit = level.find(par);
                if (lit != level.end())
                    lvl = std::max(lvl, lit->second + 1);
            }
        }
        level[id] = lvl;
    }

    std::map<int, std::vector<QString>> by_level;
    for (const auto& kv : level)
        by_level[kv.second].push_back(kv.first);
    for (const auto& kv : nodes) {
        if (level.count(kv.first))
            continue;
        int lvl = 0;
        auto p_it = parents.find(kv.first);
        if (p_it != parents.end()) {
            for (const auto& p : p_it->second) {
                auto lit = level.find(p);
                if (lit != level.end())
                    lvl = std::max(lvl, lit->second + 1);
            }
        }
        level[kv.first] = lvl;
        by_level[lvl].push_back(kv.first);
    }

    const double x_spacing = 160.0;
    const double y_spacing = 150.0;

    int lvl0_count = static_cast<int>(by_level[0].size());
    for (int i = 0; i < lvl0_count; ++i) {
        double x = (i - (lvl0_count - 1) / 2.0) * x_spacing;
        positions_[by_level[0][i]] = QPointF(x, 0.0);
    }
    qDebug() << "[viewer] Niveau" << 0 << "->" << by_level[0];

    for (auto it = std::next(by_level.begin()); it != by_level.end(); ++it) {
        auto& nodes_lvl = it->second;
        std::sort(nodes_lvl.begin(), nodes_lvl.end(), [&](const QString& a, const QString& b) {
            auto pa = parents.find(a);
            auto pb = parents.find(b);
            auto avg = [&](const std::vector<QString>& ps) {
                double sum = 0.0;
                int cnt = 0;
                for (const auto& p : ps) {
                    auto pos_it = positions_.find(p);
                    if (pos_it != positions_.end()) {
                        sum += pos_it->second.x();
                        ++cnt;
                    }
                }
                return cnt ? sum / cnt : 0.0;
            };
            double avga = (pa != parents.end()) ? avg(pa->second) : 0.0;
            double avgb = (pb != parents.end()) ? avg(pb->second) : 0.0;
            if (std::abs(avga - avgb) > 1e-3)
                return avga < avgb;
            return a < b;
        });

        double prev_x = std::numeric_limits<double>::lowest();
        for (int i = 0; i < static_cast<int>(nodes_lvl.size()); ++i) {
            const QString& id = nodes_lvl[i];
            if (nodes.at(id).external) {
                auto p_it = parents.find(id);
                double parent_mean = 0.0;
                int cnt = 0;
                if (p_it != parents.end()) {
                    for (const auto& p : p_it->second) {
                        auto pos_it = positions_.find(p);
                        if (pos_it != positions_.end()) {
                            parent_mean += pos_it->second.x();
                            ++cnt;
                        }
                    }
                }
                if (cnt)
                    parent_mean /= cnt;
                positions_[id] = QPointF(parent_mean + x_spacing * 0.4, it->first * y_spacing);
                continue;
            }
            double target = 0.0;
            auto p_it = parents.find(id);
            if (p_it != parents.end()) {
                double sum = 0.0;
                int cnt = 0;
                for (const auto& p : p_it->second) {
                    auto pos_it = positions_.find(p);
                    if (pos_it != positions_.end()) {
                        sum += pos_it->second.x();
                        ++cnt;
                    }
                }
                if (cnt)
                    target = sum / cnt;
            }
            double x = target;
            if (x < prev_x + x_spacing)
                x = prev_x + x_spacing;
            double y = it->first * y_spacing;
            positions_[id] = QPointF(x, y);
            prev_x = x;
        }
        qDebug() << "[viewer] Niveau" << it->first << "->" << nodes_lvl;
    }

    BuildGraph();
}

void GraphWindow::UseCircularLayout() {
    LayoutCircular();
}

void GraphWindow::UseTreeLayout() {
    LayoutTree();
}

void GraphWindow::DrawArrow(const QPointF& from, const QPointF& to, const QPen& pen, double node_radius,
                            double head_length, const std::optional<QPointF>& ctrl) {
    QLineF full(from, to);
    if (full.length() < 1.0)
        return;

    QPointF dir = (to - from) / full.length();
    QPointF start = from + dir * node_radius;
    QPointF end = to - dir * (node_radius + head_length * 0.6);

    QPainterPath path(start);
    if (ctrl) {
        path.quadTo(*ctrl, end);
    } else {
        path.lineTo(end);
    }
    auto* edge = scene_->addPath(path, pen);
    edge->setZValue(-1);

    QPointF tangent = ctrl ? (end - *ctrl) : (end - start);
    const double head_angle = M_PI / 6.0;
    double angle = std::atan2(tangent.y(), tangent.x());
    QPointF arrow_p1 = end + QPointF(std::cos(angle + head_angle) * head_length,
                                     std::sin(angle + head_angle) * head_length);
    QPointF arrow_p2 = end + QPointF(std::cos(angle - head_angle) * head_length,
                                     std::sin(angle - head_angle) * head_length);

    QPolygonF arrow_head;
    arrow_head << end << arrow_p1 << arrow_p2;
    auto* triangle = scene_->addPolygon(arrow_head, pen, QBrush(pen.color()));
    triangle->setZValue(0.5);
}

void GraphWindow::DrawSelfLoop(const QPointF& center, const QPen& pen, double radius) {
    const double head_len = 12.0;
    const double lift = radius * 2.2;
    const double side = radius * 1.4;

    QPointF start = center + QPointF(radius * 0.6, -radius * 0.4);
    QPointF end = center + QPointF(-radius * 0.2, -radius * 1.8);
    QPointF ctrl1 = start + QPointF(side, -lift * 0.4);
    QPointF ctrl2 = end + QPointF(side * 0.2, -lift * 0.3);

    QPainterPath path(start);
    path.cubicTo(ctrl1, ctrl2, end);
    QPen loop_pen = pen;
    loop_pen.setWidth(std::max(2, pen.width() + 1));
    auto* loop = scene_->addPath(path, loop_pen);
    loop->setZValue(0.6);

    QPointF prev = path.pointAtPercent(0.97);
    QPointF tangent = end - prev;
    const double head_angle = M_PI / 6.0;
    double angle = std::atan2(tangent.y(), tangent.x());
    QPointF arrow_p1 = end + QPointF(std::cos(angle + head_angle) * head_len,
                                     std::sin(angle + head_angle) * head_len);
    QPointF arrow_p2 = end + QPointF(std::cos(angle - head_angle) * head_len,
                                     std::sin(angle - head_angle) * head_len);
    QPolygonF arrow_head;
    arrow_head << end << arrow_p1 << arrow_p2;
    auto* triangle = scene_->addPolygon(arrow_head, loop_pen, QBrush(loop_pen.color()));
    triangle->setZValue(0.8);
}

void GraphWindow::ForceLayout(const std::vector<QString>& nodes, const std::vector<std::pair<QString, QString>>& edges,
                              const std::unordered_set<QString>& frozen) {
    if (nodes.empty())
        return;
    const double area = 60000.0 * std::max(1, static_cast<int>(nodes.size()));
    const double k = std::sqrt(area / nodes.size());
    const int iterations = 200;
    const double cooling = 0.95;
    double temperature = std::sqrt(area);

    for (int it = 0; it < iterations; ++it) {
        std::unordered_map<QString, QPointF> disp;
        for (const auto& n : nodes)
            disp[n] = QPointF(0, 0);

        for (size_t i = 0; i < nodes.size(); ++i) {
            for (size_t j = i + 1; j < nodes.size(); ++j) {
                QPointF delta = positions_[nodes[i]] - positions_[nodes[j]];
                double dist = std::hypot(delta.x(), delta.y()) + 0.01;
                double force = (k * k) / dist;
                QPointF dir = delta / dist;
                disp[nodes[i]] += dir * force;
                disp[nodes[j]] -= dir * force;
            }
        }

        for (const auto& e : edges) {
            QPointF delta = positions_[e.first] - positions_[e.second];
            double dist = std::hypot(delta.x(), delta.y()) + 0.01;
            double force = (dist * dist) / k;
            QPointF dir = delta / dist;
            disp[e.first] -= dir * force;
            disp[e.second] += dir * force;
        }

        for (const auto& n : nodes) {
            if (frozen.count(n))
                continue;
            QPointF d = disp[n];
            double norm = std::hypot(d.x(), d.y());
            if (norm > 0.0001) {
                double scale = std::min(norm, temperature) / norm;
                positions_[n] += d * scale;
            }
        }
        temperature *= cooling;
    }

    if (!positions_.empty()) {
        double minx = 1e9, maxx = -1e9, miny = 1e9, maxy = -1e9;
        for (const auto& kv : positions_) {
            minx = std::min(minx, kv.second.x());
            maxx = std::max(maxx, kv.second.x());
            miny = std::min(miny, kv.second.y());
            maxy = std::max(maxy, kv.second.y());
        }
        QPointF center((minx + maxx) / 2.0, (miny + maxy) / 2.0);
        for (auto& kv : positions_)
            kv.second -= center;
    }
}
