#include "GraphWindow.hpp"

#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonValue>
#include <QStringList>
#include <QPen>
#include <QBrush>
#include <QGraphicsEllipseItem>
#include <QGraphicsPolygonItem>
#include <QGraphicsTextItem>
#include <QToolBar>
#include <QAction>
#include <QDebug>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <queue>
#include <map>
#include <set>

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
    : QMainWindow(parent), scene_(new QGraphicsScene(this)), view_(new QGraphicsView(scene_)) {
    const QString memory_id = "memory";
    setWindowTitle("Fragment Graph Viewer");
    setCentralWidget(view_);
    view_->setRenderHint(QPainter::Antialiasing);
    view_->setDragMode(QGraphicsView::ScrollHandDrag);
    view_->setTransformationAnchor(QGraphicsView::AnchorUnderMouse);

    auto nodes = LoadSummary(summary_path);
    nodes_ = std::move(nodes);

    auto* toolbar = addToolBar("Layout");
    auto* circleAction = toolbar->addAction("Cercle");
    auto* treeAction = toolbar->addAction("Arborescence");
    connect(circleAction, &QAction::triggered, this, &GraphWindow::UseCircularLayout);
    connect(treeAction, &QAction::triggered, this, &GraphWindow::UseTreeLayout);

    auto children = BuildChildren();
    DetectCycles(children);
    LayoutCircular();
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
    std::unordered_map<QString, QString> external_display;
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
                // Cas typique : id="func_9_transform", appel externe "transform".
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

    // Insérer les appels externes comme noeuds dédiés.
    for (const auto& item : partitions_val.toArray()) {
        if (!item.isObject())
            continue;
        QJsonObject obj = item.toObject();
        QString caller = obj.value("id").toString();
        auto ext_calls = obj.value("external_calls");
        auto unresolved = obj.value("unresolved_calls");
        auto part_libs = obj.value("required_libraries");
        // Ajouter les libs globales aussi
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
                // Si la cible correspond à une partition connue (full id ou suffixe), relier en interne.
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

    // Libs globales du summary
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

    // Mémoire globale
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

void GraphWindow::BuildGraph() {
    scene_->clear();
    const double node_radius = 22.0;
    const double arrow_head = 16.0;
    QPen edge_pen(Qt::gray);
    edge_pen.setWidth(2);

    auto children = BuildChildren();
    auto order = TopologicalOrder(children);
    if (order.empty()) {
        order.reserve(nodes_.size());
        for (const auto& pair : nodes_)
            order.push_back(pair.first);
    }
    std::unordered_map<QString, int> order_index;
    for (int i = 0; i < static_cast<int>(order.size()); ++i)
        order_index[order[i]] = i + 1;  // 1-based for affichage

    std::vector<QString> draw_ids = order;
    for (const auto& kv : nodes_) {
        if (std::find(draw_ids.begin(), draw_ids.end(), kv.first) == draw_ids.end())
            draw_ids.push_back(kv.first);
    }

    for (const auto& id : draw_ids) {
        const auto& node = nodes_.at(id);
        QPointF center = positions_[node.id];
        QRectF ellipse(center.x() - node_radius, center.y() - node_radius, node_radius * 2, node_radius * 2);
        QPen node_pen(Qt::black);
        const bool is_cycle = cycle_nodes_.count(node.id.toStdString()) > 0;
        if (is_cycle)
            node_pen.setColor(Qt::red);
        auto ellipse_item = scene_->addEllipse(ellipse, node_pen, QBrush(NodeColor(node.parallel, node.external, node.memory)));
        ellipse_item->setToolTip(BuildTooltip(node));

        QString label = node.label.isEmpty() ? node.id : node.label;
        auto idx_it = order_index.find(node.id);
        if (idx_it != order_index.end())
            label = QString::number(idx_it->second) + " · " + label;
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
            const bool in_cycle = cycle_edges_.count(EdgeKey(dep, node.id)) > 0;
            QPen pen = in_cycle ? QPen(Qt::red) : edge_pen;
            pen.setWidth(is_memory_edge ? 1 : (in_cycle ? 3 : 2));
            pen.setStyle(is_memory_edge ? Qt::DotLine : (in_cycle ? Qt::DashLine : Qt::SolidLine));

            // Arcs pour liens bidirectionnels (plus lisible qu'une ligne superposée).
            std::optional<QPointF> ctrl;
            const bool bidirectional = HasReverseEdge(node.id, dep);
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

        // Si le nœud appartient à un cycle mais aucune auto-dépendance explicite n'est fournie,
        // ajouter une boucle implicite pour signaler la récursivité dans le SCC.
        if (!has_self_loop && (cycle_nodes_.count(node.id.toStdString()) || node.self_call)) {
            QPen loop_pen(Qt::red);
            loop_pen.setWidth(2);
            loop_pen.setStyle(Qt::DashLine);
            DrawSelfLoop(center, loop_pen, node_radius);
        }
    }

    view_->fitInView(scene_->itemsBoundingRect(), Qt::KeepAspectRatio);
}

QString GraphWindow::BuildTooltip(const GraphWindow::Node& node) const {
    QStringList lines;
    lines << node.label;
    if (!node.start.isEmpty())
        lines << QString("Adresse: %1 - %2 (%3 o)").arg(node.start, node.end).arg(node.size);
    if (!node.inputs.empty())
        lines << "Entrées: " + QStringList(node.inputs.begin(), node.inputs.end()).join(", ");
    if (!node.outputs.empty())
        lines << "Sorties: " + QStringList(node.outputs.begin(), node.outputs.end()).join(", ");
    if (!node.external_inputs.empty())
        lines << "Entrées externes: " + QStringList(node.external_inputs.begin(), node.external_inputs.end()).join(", ");
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
        lines << "Mémoire globale";
    if (node.external)
        lines << "Externe";
    return lines.join("\n");
}

std::unordered_map<QString, std::vector<QString>> GraphWindow::BuildChildren() const {
    std::unordered_map<QString, std::vector<QString>> children;
    for (const auto& pair : nodes_) {
        for (const auto& dep : pair.second.deps)
            children[pair.first].push_back(dep);
    }
    return children;
}

void GraphWindow::DetectCycles(const std::unordered_map<QString, std::vector<QString>>& children) {
    cycle_edges_.clear();
    cycle_nodes_.clear();
    for (const auto& kv : nodes_) {
        if (kv.second.self_call) {
            cycle_nodes_.insert(kv.first.toStdString());
            cycle_edges_.insert(EdgeKey(kv.first, kv.first));
            qDebug() << "[viewer] Auto-appel détecté pour" << kv.first;
        }
    }
    // Tarjan SCC
    std::unordered_map<QString, int> index;
    std::unordered_map<QString, int> lowlink;
    std::unordered_map<QString, bool> on_stack;
    std::vector<QString> stack;
    int current_index = 0;

    std::function<void(const QString&)> dfs = [&](const QString& u) {
        index[u] = lowlink[u] = current_index++;
        stack.push_back(u);
        on_stack[u] = true;

        auto it = children.find(u);
        if (it != children.end()) {
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
            qDebug() << "[viewer] SCC détecté:" << scc << "self_loop?" << self_loop;
            for (const auto& n : scc)
                cycle_nodes_.insert(n.toStdString());
            // Marquer les arêtes internes à la SCC
            for (const auto& n : scc) {
                const auto& node = nodes_.at(n);
                    for (const auto& d : node.deps) {
                        if (std::find(scc.begin(), scc.end(), d) != scc.end()) {
                            cycle_edges_.insert(EdgeKey(d, n));
                            qDebug() << "[viewer]   arête cycle" << d << "->" << n;
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

std::vector<QString> GraphWindow::TopologicalOrder(const std::unordered_map<QString, std::vector<QString>>& children) const {
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

        auto child_it = children.find(id);
        if (child_it == children.end())
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

    // En cas de cycles, placer aussi les noeuds restants pour éviter les trous.
    if (order.size() != nodes_.size()) {
        for (const auto& kv : indegree) {
            if (std::find(order.begin(), order.end(), kv.first) == order.end())
                order.push_back(kv.first);
        }
    }
    return order;
}

bool GraphWindow::HasReverseEdge(const QString& from, const QString& to) const {
    auto it = nodes_.find(to);
    if (it == nodes_.end())
        return false;
    return std::find(it->second.deps.begin(), it->second.deps.end(), from) != it->second.deps.end();
}

void GraphWindow::LayoutCircular() {
    const double radius = 250.0;
    positions_.clear();
    const QString memory_id = "memory";
    auto children = BuildChildren();
    auto order = TopologicalOrder(children);
    if (order.empty()) {
        order.reserve(nodes_.size());
        for (const auto& pair : nodes_)
            order.push_back(pair.first);
    }
    const int n = static_cast<int>(order.size());
    for (int idx = 0; idx < n; ++idx) {
        double angle = (2 * M_PI * idx) / std::max(1, n);
        positions_[order[idx]] = QPointF(radius * std::cos(angle), radius * std::sin(angle));
    }
    int extra = n;
    for (const auto& kv : nodes_) {
        if (positions_.count(kv.first))
            continue;
        double angle = (2 * M_PI * extra) / std::max(1, static_cast<int>(nodes_.size()));
        positions_[kv.first] = QPointF(radius * std::cos(angle), radius * std::sin(angle));
        ++extra;
    }

    // Spatialisation force-directed pour limiter les croisements.
    std::vector<std::pair<QString, QString>> edges;
    for (const auto& pair : nodes_) {
        for (const auto& dep : pair.second.deps)
            edges.emplace_back(pair.first, dep);
    }
    std::vector<QString> all_ids;
    all_ids.reserve(nodes_.size());
    for (const auto& kv : nodes_)
        all_ids.push_back(kv.first);
    std::unordered_set<QString> frozen;
    if (positions_.count(memory_id))
        frozen.insert(memory_id);
    ForceLayout(all_ids, edges, frozen);

    // Placer la mémoire à l'extérieur du cercle pour réduire la surcharge visuelle.
    if (positions_.count(memory_id)) {
        QPointF center(0, 0);
        double max_r = radius + 200;
        positions_[memory_id] = QPointF(max_r, -max_r * 0.3);
    }

    BuildGraph();
}

void GraphWindow::LayoutTree() {
    positions_.clear();
    auto children = BuildChildren();
    auto order = TopologicalOrder(children);
    if (order.empty()) {
        order.reserve(nodes_.size());
        for (const auto& pair : nodes_)
            order.push_back(pair.first);
    }

    // parents: callee -> list of callers
    std::unordered_map<QString, std::vector<QString>> parents;
    for (const auto& pair : nodes_) {
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
    // Placer aussi les noeuds externes/lib/mémoire à +1 de leurs parents (ou 0).
    for (const auto& kv : nodes_) {
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

    // Position niveau par niveau pour limiter les croisements :
    // - niveau 0 : order stable
    // - niveaux suivants : tri par moyenne des x des parents, puis maintien d'un espacement minimal.
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
            if (nodes_.at(id).external) {
                // Positionner les noeuds externes juste après leurs parents moyens.
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

std::string GraphWindow::EdgeKey(const QString& from, const QString& to) const {
    return from.toStdString() + "->" + to.toStdString();
}

void GraphWindow::DrawSelfLoop(const QPointF& center, const QPen& pen, double radius) {
    // Boucle stylisée : courbe cubique façon "noeud" DFA.
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

        // Répulsion
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

        // Attraction
        for (const auto& e : edges) {
            QPointF delta = positions_[e.first] - positions_[e.second];
            double dist = std::hypot(delta.x(), delta.y()) + 0.01;
            double force = (dist * dist) / k;
            QPointF dir = delta / dist;
            disp[e.first] -= dir * force;
            disp[e.second] += dir * force;
        }

        // Appliquer déplacements limités par la température
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

    // Recentrer
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
