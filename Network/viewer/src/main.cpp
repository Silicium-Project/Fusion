#include <QApplication>
#include <QMessageBox>
#include <QTranslator>
#include <QDir>
#include <QLocale>
#include <QStringList>

#include "GraphWindow.hpp"

namespace {

QString normalizeLocale(QString locale) {
    locale = locale.trimmed();
    if (locale.isEmpty())
        return QString();
    locale = locale.split('.').first();
    locale = locale.split('@').first();
    locale.replace('-', '_');
    return locale;
}

}  // namespace

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);

    const QString envLocale = normalizeLocale(qEnvironmentVariable("SILICIUM_LOCALE"));
    const QString sysLocale = QLocale::system().name();  // e.g. fr_FR
    const QString locale = envLocale.isEmpty() ? sysLocale : envLocale;

    QTranslator translator;
    const QString translationsDir =
        QDir(QCoreApplication::applicationDirPath()).filePath("translations");
    translator.load("fragment_viewer_" + locale, translationsDir);
    if (!translator.isEmpty())
        app.installTranslator(&translator);

    QStringList args = app.arguments();
    if (args.size() < 2) {
        QMessageBox::information(
            nullptr,
            QCoreApplication::translate("main", "Usage"),
            QCoreApplication::translate("main", "Usage: fragment_viewer <path/to/summary.json>"));
        return 1;
    }

    try {
        GraphWindow window(args[1]);
        window.resize(800, 600);
        window.show();
        return app.exec();
    } catch (const std::exception& e) {
        QMessageBox::critical(
            nullptr, QCoreApplication::translate("main", "Error"), QString::fromUtf8(e.what()));
        return 1;
    }
}

