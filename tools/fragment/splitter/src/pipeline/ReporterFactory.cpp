#include "pipeline/ReporterFactory.hpp"

#include <algorithm>
#include <fstream>

#include "pipeline/ConsoleReporter.hpp"
#include "pipeline/JsonReporter.hpp"
#include "pipeline/MultiReporter.hpp"
#include "support/Env.hpp"

namespace splitter {

namespace {

std::string Normalize(std::string value, const std::string& env_var) {
    if (value.empty())
        if (auto env = GetEnv(env_var))
            value = *env;
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}

}  // namespace

std::unique_ptr<IReporter> ReporterFactory::Create(const PipelineConfig& config) {
    const std::string mode = Normalize(config.reporter, "SPLITTER_REPORTER");
    std::string file_path = config.report_file;
    if (file_path.empty())
        if (auto env = GetEnv("SPLITTER_REPORT_FILE"))
            file_path = *env;

    auto make_single = [&]() -> std::unique_ptr<IReporter> {
        if (mode == "json" || mode == "ndjson")
            return std::make_unique<JsonReporter>();
        return std::make_unique<ConsoleReporter>();
    };

    if (file_path.empty())
        return make_single();

    auto stream = std::make_shared<std::ofstream>(file_path);
    if (!(*stream)) {
        // Fallback console si le fichier ne peut pas s'ouvrir.
        return make_single();
    }

    std::vector<std::unique_ptr<IReporter>> reporters;
    reporters.push_back(make_single());
    if (mode == "json" || mode == "ndjson")
        reporters.push_back(std::make_unique<JsonReporter>(stream));
    else
        reporters.push_back(std::make_unique<ConsoleReporter>());
    return std::make_unique<MultiReporter>(std::move(reporters));
}

}  // namespace splitter
