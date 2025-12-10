#pragma once

#include <QGraphicsScene>
#include <QGraphicsView>
#include <QMainWindow>
#include <QJsonObject>
#include <QJsonArray>
#include <QString>
#include <unordered_map>
#include <vector>

class GraphWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit GraphWindow(const QString& summary_path, QWidget* parent = nullptr);

private:
    struct Node {
        QString id;
        bool parallel = false;
        std::vector<QString> deps;
    };

    QGraphicsScene* scene_;
    QGraphicsView* view_;

    std::unordered_map<QString, Node> LoadSummary(const QString& path) const;
    void BuildGraph(const std::unordered_map<QString, Node>& nodes);
};

