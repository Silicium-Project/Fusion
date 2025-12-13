#include "pipeline/ReporterFactory.hpp"

#include <algorithm>
#include <fstream>

#include "pipeline/ConsoleReporter.hpp"
#include "pipeline/JsonReporter.hpp"
#include "pipeline/MultiReporter.hpp"
#include "support/Env.hpp"

namespace splitter {

namespace {

constexpr std::string_view kReporterConsole = "console";
constexpr std::string_view kReporterJson = "json";
constexpr std::string_view kReporterNdJson = "ndjson";

std::string Normalize(std::string value, const std::string& env_var) {
    if (value.empty())
        if (auto env = GetEnv(env_var))
            value = *env;
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}

}  // namespace

std::shared_ptr<IReporter> ReporterFactory::Create(const PipelineConfig& config) {
    const std::string mode = Normalize(config.reporter, "SPLITTER_REPORTER");
    std::string file_path = config.report_file;
    if (file_path.empty())
        if (auto env = GetEnv("SPLITTER_REPORT_FILE"))
            file_path = *env;

    auto make_single = [&]() -> std::shared_ptr<IReporter> {
        if (mode == kReporterJson || mode == kReporterNdJson)
            return std::make_shared<JsonReporter>();
        return std::make_shared<ConsoleReporter>();
    };

    if (file_path.empty())
        return make_single();

    auto stream = std::make_shared<std::ofstream>(file_path);
    if (!(*stream)) {
        // Fallback console si le fichier ne peut pas s'ouvrir.
        return make_single();
    }

    std::vector<std::shared_ptr<IReporter>> reporters;
    reporters.push_back(make_single());
    if (mode == kReporterJson || mode == kReporterNdJson)
        reporters.push_back(std::make_shared<JsonReporter>(stream));
    else
        reporters.push_back(std::make_shared<ConsoleReporter>());
    return std::make_shared<MultiReporter>(std::move(reporters));
}

}  // namespace splitter
