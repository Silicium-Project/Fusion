#include <QApplication>
#include <QMessageBox>
#include <QStringList>

#include "GraphWindow.hpp"

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    QStringList args = app.arguments();
    if (args.size() < 2) {
        QMessageBox::information(nullptr, "Usage", "Usage: fragment_viewer <path/to/summary.json>");
        return 1;
    }

    try {
        GraphWindow window(args[1]);
        window.resize(800, 600);
        window.show();
        return app.exec();
    } catch (const std::exception& e) {
        QMessageBox::critical(nullptr, "Erreur", e.what());
        return 1;
    }
}

